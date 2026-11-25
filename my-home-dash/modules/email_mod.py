"""
Email module — fetches unread email summaries from all 4 configured accounts.

Accounts: work Outlook, home Outlook, Gmail #1, Gmail #2
Each account: unread count + subject-line previews
Returns a list of account results; failed accounts show an error message.

Gmail accounts use IMAP with an App Password when GMAIL_<n>_ADDRESS /
GMAIL_<n>_APP_PASSWORD are set in .env -- no Google Cloud OAuth project needed,
and app passwords are immune to the periodic re-auth prompts that unverified
OAuth apps hit (their refresh tokens expire every 7 days). Falls back to the
original OAuth path (auth/google_client.py) when those env vars are absent.
"""

import base64
import imaplib
import json
import logging
import os
import re
from datetime import datetime, timezone
from email import message_from_bytes
from email.header import decode_header
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

from auth.microsoft_client import get_headers
from auth.google_client import get_gmail_service
from config_loader import get_config

log = logging.getLogger(__name__)
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_GMAIL_ENV_PREFIX = {"gmail_1": "GMAIL_1", "gmail_2": "GMAIL_2"}

# ── TypeSafe Jev triage (optional, see email.jev_classification in config.yaml) ─
TYPESAFE_API_URL = "https://api.typesafe.ai/v1/systemone"
_DEFAULT_JEV_CATEGORIES = {
    "urgent": "Time-sensitive; needs a response or action today",
    "action_needed": "Requires a reply or task, but isn't urgent",
    "informational": "Newsletter, notification, or FYI with nothing to do",
    "low_priority": "Promotional, automated, or safe to ignore",
}

# ── Home Outlook folder organizer (Inbox only) ─────────────────────────────────
# Separate from the read-only unread-summary path above: this talks to Graph
# on demand (not on the scheduler's cache cycle) so folder switches and moves
# reflect the mailbox in real time.

# Junk is deliberately excluded: junk mail stays in Junk so it can be deleted
# there; it should never be moved out unless it isn't actually junk.
_ORGANIZER_FOLDERS = {"inbox": "inbox"}
_FOLDER_NAME_STRIP_RE = re.compile(r'[\\/:*?"<>|#]')
_MAILBOX_STRUCTURE_PATH = Path(__file__).resolve().parent.parent / "data" / "outlook_folder_structure.json"
MAX_MOVE_PER_ACTION = 300


# ── Microsoft accounts ────────────────────────────────────────────────────────

def _fetch_microsoft_email(account_id: str, label: str, max_subjects: int) -> dict:
    """Fetch unread emails from a Microsoft Graph account."""
    headers = get_headers(account_id)
    if not headers:
        return {
            "id": account_id, "label": label, "type": "microsoft",
            "error": f"Not authenticated. Run auth/setup_microsoft_{account_id.replace('_outlook','')}.py",
        }
    url = (
        f"{GRAPH_BASE}/me/mailFolders/Inbox/messages"
        f"?$filter=isRead eq false"
        f"&$select=subject,from,receivedDateTime"
        f"&$orderby=receivedDateTime desc"
        f"&$top={max_subjects}"
    )
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        messages = data.get("value", [])

        # Get total unread count
        count_url = f"{GRAPH_BASE}/me/mailFolders/Inbox?$select=unreadItemCount"
        count_resp = requests.get(count_url, headers=headers, timeout=10)
        unread_count = count_resp.json().get("unreadItemCount", len(messages)) if count_resp.ok else len(messages)

        subjects = []
        for m in messages:
            sender = m.get("from", {}).get("emailAddress", {}).get("name", "Unknown")
            subject = m.get("subject", "(No subject)")
            entry = {
                "subject": subject,
                "from": sender,
                "received": m.get("receivedDateTime", "")[:16].replace("T", " "),
            }
            category = _classify_with_jev(subject, sender)
            if category:
                entry["category"] = category
            subjects.append(entry)

        return {"id": account_id, "label": label, "type": "microsoft",
                "unread_count": unread_count, "subjects": subjects}

    except Exception as exc:
        log.error("Email fetch failed for %s: %s", account_id, exc)
        return {"id": account_id, "label": label, "type": "microsoft", "error": str(exc)}


# ── Google / Gmail accounts ───────────────────────────────────────────────────

def _decode_mime_words(value: str) -> str:
    if not value:
        return ""
    parts = []
    for text, charset in decode_header(value):
        if isinstance(text, bytes):
            try:
                parts.append(text.decode(charset or "utf-8", errors="replace"))
            except LookupError:
                parts.append(text.decode("utf-8", errors="replace"))
        else:
            parts.append(text)
    return "".join(parts)


def _fetch_gmail_imap(address: str, app_password: str, max_subjects: int) -> dict:
    """Fetch unread emails via IMAP using a Google App Password."""
    conn = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=15)
    try:
        conn.login(address, app_password)
        conn.select("INBOX", readonly=True)

        status, data = conn.search(None, "UNSEEN")
        if status != "OK":
            raise RuntimeError(f"IMAP UNSEEN search failed: {status}")
        message_ids = data[0].split()
        unread_count = len(message_ids)

        subjects = []
        for msg_id in message_ids[-max_subjects:][::-1]:
            status, msg_data = conn.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            parsed = message_from_bytes(msg_data[0][1])
            received = ""
            date_header = parsed.get("Date", "")
            if date_header:
                try:
                    received = parsedate_to_datetime(date_header).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    received = date_header[:16]
            subject = _decode_mime_words(parsed.get("Subject", "")) or "(No subject)"
            sender = _decode_mime_words(parsed.get("From", "")) or "Unknown"
            entry = {"subject": subject, "from": sender, "received": received}
            category = _classify_with_jev(subject, sender)
            if category:
                entry["category"] = category
            subjects.append(entry)

        return {"unread_count": unread_count, "subjects": subjects}
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def _fetch_gmail(account_id: str, label: str, max_subjects: int) -> dict:
    """Fetch unread emails for a Gmail account: IMAP app password if configured,
    otherwise fall back to the OAuth path."""
    env_prefix = _GMAIL_ENV_PREFIX.get(account_id)
    address = os.getenv(f"{env_prefix}_ADDRESS", "").strip() if env_prefix else ""
    app_password = os.getenv(f"{env_prefix}_APP_PASSWORD", "").strip() if env_prefix else ""

    if address and app_password:
        try:
            result = _fetch_gmail_imap(address, app_password, max_subjects)
            return {"id": account_id, "label": label, "type": "google", **result}
        except Exception as exc:
            log.error("Gmail IMAP fetch failed for %s: %s", account_id, exc)
            return {"id": account_id, "label": label, "type": "google", "error": str(exc)}

    return _fetch_gmail_oauth(account_id, label, max_subjects)


def _fetch_gmail_oauth(account_id: str, label: str, max_subjects: int) -> dict:
    """Fetch unread emails from a Gmail account via the Google OAuth path."""
    service = get_gmail_service(account_id)
    if service is None:
        return {
            "id": account_id, "label": label, "type": "google",
            "error": "Not authenticated. Run auth/setup_google.py",
        }
    try:
        # Get unread count from INBOX label
        label_info = service.users().labels().get(userId="me", id="INBOX").execute()
        unread_count = label_info.get("messagesUnread", 0)

        # Fetch subject lines
        result = service.users().messages().list(
            userId="me", labelIds=["INBOX", "UNREAD"], maxResults=max_subjects
        ).execute()
        messages = result.get("messages", [])

        subjects = []
        for msg_ref in messages:
            try:
                msg = service.users().messages().get(
                    userId="me", id=msg_ref["id"], format="metadata",
                    metadataHeaders=["Subject", "From", "Date"]
                ).execute()
                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                date_str = headers.get("Date", "")[:16]
                subject = headers.get("Subject", "(No subject)")
                sender = headers.get("From", "Unknown")
                entry = {"subject": subject, "from": sender, "received": date_str}
                category = _classify_with_jev(subject, sender)
                if category:
                    entry["category"] = category
                subjects.append(entry)
            except Exception as inner:
                log.debug("Skipping Gmail message: %s", inner)

        return {"id": account_id, "label": label, "type": "google",
                "unread_count": unread_count, "subjects": subjects}

    except Exception as exc:
        log.error("Gmail fetch failed for %s: %s", account_id, exc)
        return {"id": account_id, "label": label, "type": "google", "error": str(exc)}


def _classify_with_jev(subject: str, sender: str) -> str | None:
    """Triage one message into a category using TypeSafe's Jev model.

    Best-effort: disabled by default (email.jev_classification.enabled in
    config.yaml) and requires TYPESAFE_API_KEY in .env. Any failure (missing
    key, network error, disabled) returns None so callers just omit the
    category rather than blocking the email fetch.
    """
    jev_cfg = get_config().get("email", {}).get("jev_classification", {})
    if not jev_cfg.get("enabled", False):
        return None

    api_key = os.getenv("TYPESAFE_API_KEY", "").strip()
    if not api_key:
        return None

    categories = jev_cfg.get("categories") or _DEFAULT_JEV_CATEGORIES

    try:
        resp = requests.post(
            TYPESAFE_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "state": f"Subject: {subject or '(no subject)'}\nFrom: {sender or 'Unknown'}",
                "model": "jev-latest",
                "questions": {
                    "category": {
                        "type": "choice",
                        "instructions": "Which category best fits this email?",
                        "criteria": categories,
                    }
                },
            },
            timeout=int(jev_cfg.get("timeout_seconds", 5)),
        )
        resp.raise_for_status()
        return resp.json().get("answers", {}).get("category", {}).get("choice")
    except Exception as exc:
        log.warning("Jev classification failed: %s", exc)
        return None


def sanitize_folder_name(raw: str, fallback: str = "Sorted Mail") -> str:
    """Strip characters Outlook rejects in folder names and cap the length."""
    cleaned = _FOLDER_NAME_STRIP_RE.sub("", raw or "").strip()
    return (cleaned or fallback)[:50]


def list_folder_messages(account_id: str, folder_key: str, max_items: int = 20) -> dict:
    """Recent messages (read or unread) from the Inbox, for the folder-organizer UI."""
    headers = get_headers(account_id)
    if not headers:
        return {"error": "Not authenticated. Run auth/setup_microsoft_home.py"}

    folder = _ORGANIZER_FOLDERS.get(folder_key, "inbox")
    url = (
        f"{GRAPH_BASE}/me/mailFolders/{folder}/messages"
        f"?$select=subject,from,receivedDateTime,isRead"
        f"&$orderby=receivedDateTime desc"
        f"&$top={max_items}"
    )
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        messages = []
        for m in resp.json().get("value", []):
            addr = (m.get("from") or {}).get("emailAddress") or {}
            messages.append({
                "subject": m.get("subject") or "(No subject)",
                "from_name": addr.get("name") or addr.get("address", "Unknown"),
                "from_address": addr.get("address", ""),
                "received": m.get("receivedDateTime", "")[:16].replace("T", " "),
                "is_read": m.get("isRead", True),
            })
        return {"messages": messages}
    except Exception as exc:
        log.error("Folder fetch failed for %s/%s: %s", account_id, folder_key, exc)
        return {"error": str(exc)}


def _base_domain(address: str) -> str:
    """Best-effort registrable-domain extraction (last two dot-separated labels).

    Companies routinely send from many different subdomains or even a unique
    address per message (e.g. AT&T order-status mail comes from a fresh
    "attorderstatus.<id>@<one-of-several-subdomains>.att-mail.com" every time) --
    exact-address matching would treat every one of those as a different sender.
    Matching on the base domain instead groups them correctly. This doesn't
    consult a public-suffix list, so multi-part TLDs like ".co.uk" would
    collapse incorrectly -- an accepted simplification for personal use.
    """
    if "@" not in address:
        return address.lower()
    domain = address.rsplit("@", 1)[-1].lower()
    labels = domain.split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else domain


def _fetch_folder_from_addresses(headers: dict, folder: str, page_size: int = 250) -> list[tuple[str, str]]:
    """Paginate the whole folder once, returning (message_id, from_address) pairs.

    Graph's mail $filter doesn't support endsWith/contains on the nested
    from/emailAddress/address property -- confirmed directly against the live API
    (400 ErrorInvalidUrlQueryFilter) -- so domain-based matching has to scan
    client-side rather than filter server-side like exact-address matching could.
    """
    url = f"{GRAPH_BASE}/me/mailFolders/{folder}/messages"
    params = {"$select": "id,from", "$top": page_size}
    results: list[tuple[str, str]] = []
    while url:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        for m in payload.get("value", []):
            addr = ((m.get("from") or {}).get("emailAddress") or {}).get("address") or ""
            results.append((m["id"], addr))
        url = payload.get("@odata.nextLink")
        params = None
    return results


def _infer_group_name_via_llm(subject: str, from_name: str) -> str | None:
    """Ask the local model for a folder name when a message has no return address.

    There's no sender identity to derive a name from in that case, so the locally
    loaded model (same Bonsai runtime the dashboard's chat card uses, see
    support/local_ai/) proposes one from the subject and displayed sender name
    instead. Best-effort: any failure (server unreachable, empty reply, timeout)
    returns None so callers fall back to sanitize_folder_name()'s default rather
    than blocking the archive action.
    """
    llm_cfg = get_config().get("llm", {})
    base_url = llm_cfg.get("bonsai_base_url", "http://127.0.0.1:1080")
    model = llm_cfg.get("bonsai_model", "bonsai2-27b")
    timeout_seconds = int(llm_cfg.get("timeout_seconds", 90))

    prompt = (
        "An email arrived with no usable return address, so it can't be filed by sender. "
        "Suggest a short folder name (2-4 words, title case, no punctuation) that best "
        "describes where to file it, based on this data:\n"
        f"Subject: {subject or '(no subject)'}\n"
        f"Displayed sender name: {from_name or '(unknown)'}\n"
        "Reply with ONLY the folder name, nothing else."
    )
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "temperature": 0.2,
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        choice = (response.json().get("choices") or [{}])[0]
        content = str((choice.get("message") or {}).get("content", "")).strip()
        return content or None
    except Exception as exc:
        log.warning("Folder-name inference failed: %s", exc)
        return None


def count_sender_messages(
    account_id: str, folder_key: str, sender_address: str, subject: str = "", from_name: str = ""
) -> dict:
    """Total messages sharing this sender's base domain in the given folder.

    Messages with no return address at all can't be matched by domain, so they're
    grouped together as one pseudo-sender instead; the suggested folder name for
    that group comes from `_infer_group_name_via_llm`.
    """
    headers = get_headers(account_id)
    if not headers:
        return {"error": "Not authenticated."}

    folder = _ORGANIZER_FOLDERS.get(folder_key, "inbox")
    try:
        entries = _fetch_folder_from_addresses(headers, folder)
    except Exception as exc:
        log.error("Sender count failed for %s: %s", account_id, exc)
        return {"error": str(exc)}

    if not sender_address:
        count = sum(1 for _msg_id, addr in entries if not addr)
        suggested = _infer_group_name_via_llm(subject, from_name)
        return {
            "count": count,
            "no_return_address": True,
            "suggested_name": sanitize_folder_name(suggested or "", fallback="Unsorted (No Address)"),
        }

    domain = _base_domain(sender_address)
    count = sum(1 for _msg_id, addr in entries if _base_domain(addr) == domain)
    return {"count": count}


def _find_child_folder(headers: dict, parent_id: str | None, display_name: str) -> dict | None:
    safe_name = display_name.replace("'", "''")
    url = (
        f"{GRAPH_BASE}/me/mailFolders"
        if parent_id is None
        else f"{GRAPH_BASE}/me/mailFolders/{parent_id}/childFolders"
    )
    resp = requests.get(
        url,
        headers=headers,
        params={"$filter": f"displayName eq '{safe_name}'", "$select": "id,displayName"},
        timeout=15,
    )
    resp.raise_for_status()
    existing = resp.json().get("value", [])
    return existing[0] if existing else None


def _list_folders(headers: dict, parent_id: str | None = None) -> list[dict]:
    url = (
        f"{GRAPH_BASE}/me/mailFolders"
        if parent_id is None
        else f"{GRAPH_BASE}/me/mailFolders/{parent_id}/childFolders"
    )
    params = {
        "includeHiddenFolders": "true",
        "$select": "id,displayName,parentFolderId,childFolderCount",
        "$top": 100,
    }
    folders = []
    while url:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        folders.extend(payload.get("value", []))
        url = payload.get("@odata.nextLink")
        params = None
    return folders


def _sync_mailbox_structure(headers: dict) -> dict:
    folders = []

    def collect(parent_id: str | None, parent_path: str | None) -> None:
        for folder in _list_folders(headers, parent_id):
            path = f"{parent_path}/{folder['displayName']}" if parent_path else folder["displayName"]
            folders.append({
                "id": folder["id"],
                "parent_id": folder.get("parentFolderId"),
                "display_name": folder["displayName"],
                "path": path,
            })
            if folder.get("childFolderCount", 0):
                collect(folder["id"], path)

    collect(None, None)
    structure = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "folders": folders,
    }
    _MAILBOX_STRUCTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = _MAILBOX_STRUCTURE_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(structure, indent=2), encoding="utf-8")
    os.replace(temporary_path, _MAILBOX_STRUCTURE_PATH)
    return structure


def _folder_by_path(structure: dict, path: str) -> dict | None:
    wanted = path.casefold()
    return next(
        (folder for folder in structure["folders"] if folder["path"].casefold() == wanted),
        None,
    )


def _find_or_create_folder(headers: dict, display_name: str, structure: dict) -> dict:
    """Reuse a folder under Mail Box, or create it under Legacy & Unsorted."""
    mailbox = _folder_by_path(structure, "Mail Box")
    if not mailbox:
        raise RuntimeError("Outlook folder 'Mail Box' was not found.")

    mailbox_prefix = "mail box/"
    matches = [
        folder for folder in structure["folders"]
        if folder["path"].casefold().startswith(mailbox_prefix)
        and folder["display_name"].casefold() == display_name.casefold()
    ]
    if len(matches) == 1:
        return {"id": matches[0]["id"], "path": matches[0]["path"], "created": False}
    if len(matches) > 1:
        paths = ", ".join(folder["path"] for folder in matches)
        raise RuntimeError(f"Multiple Outlook folders are named '{display_name}': {paths}")

    fallback = _folder_by_path(structure, "Mail Box/Legacy & Unsorted")
    if not fallback:
        fallback_resp = requests.post(
            f"{GRAPH_BASE}/me/mailFolders/{mailbox['id']}/childFolders",
            headers=headers,
            json={"displayName": "Legacy & Unsorted"},
            timeout=15,
        )
        fallback_resp.raise_for_status()
        fallback = fallback_resp.json()

    create_resp = requests.post(
        f"{GRAPH_BASE}/me/mailFolders/{fallback['id']}/childFolders",
        headers=headers,
        json={"displayName": display_name},
        timeout=15,
    )
    create_resp.raise_for_status()
    created = create_resp.json()
    _sync_mailbox_structure(headers)
    return {
        "id": created["id"],
        "path": f"Mail Box/Legacy & Unsorted/{display_name}",
        "created": True,
    }


def _fetch_sender_message_ids(headers: dict, folder: str, sender_address: str, limit: int) -> list[str]:
    """Message ids sharing this sender's base domain, or every no-return-address message if blank."""
    entries = _fetch_folder_from_addresses(headers, folder)
    if not sender_address:
        ids = [msg_id for msg_id, addr in entries if not addr]
    else:
        domain = _base_domain(sender_address)
        ids = [msg_id for msg_id, addr in entries if _base_domain(addr) == domain]
    return ids[:limit]


def _batch_move(headers: dict, message_ids: list[str], dest_folder_id: str) -> int:
    """Move messages via Graph's $batch endpoint (20 sub-requests per batch)."""
    moved = 0
    for i in range(0, len(message_ids), 20):
        chunk = message_ids[i:i + 20]
        batch_body = {
            "requests": [
                {
                    "id": str(j),
                    "method": "POST",
                    "url": f"/me/messages/{msg_id}/move",
                    "headers": {"Content-Type": "application/json"},
                    "body": {"destinationId": dest_folder_id},
                }
                for j, msg_id in enumerate(chunk)
            ]
        }
        resp = requests.post(f"{GRAPH_BASE}/$batch", headers=headers, json=batch_body, timeout=30)
        resp.raise_for_status()
        for item in resp.json().get("responses", []):
            if 200 <= item.get("status", 0) < 300:
                moved += 1
            else:
                log.warning("Batch move sub-request failed: %s", item)
    return moved


def _find_or_create_rule(headers: dict, sender_address: str, dest_folder_id: str, display_name: str) -> dict:
    """Idempotent: reuse an existing Inbox rule for this sender's domain if one exists, else create one.

    Uses a senderContains condition on the base domain rather than an exact
    fromAddresses match -- Graph's fromAddresses condition only ever matches one
    literal address, which is useless for senders like AT&T order-status mail
    that send every message from a newly generated address. Matching on the
    domain substring is what actually catches "future emails from this sender."

    Inbox rules only apply to mail Outlook routes to the Inbox -- server-side junk
    filtering happens upstream of rule evaluation, so a rule alone can't guarantee
    future mail from a sender currently landing in Junk will be intercepted.
    """
    domain = _base_domain(sender_address)
    rules_url = f"{GRAPH_BASE}/me/mailFolders/inbox/messageRules"
    resp = requests.get(rules_url, headers=headers, timeout=15)
    resp.raise_for_status()
    existing_rules = resp.json().get("value", [])

    for rule in existing_rules:
        for term in (rule.get("conditions", {}) or {}).get("senderContains", []) or []:
            if term.lower() == domain:
                actions = rule.get("actions") or {}
                if actions.get("moveToFolder") == dest_folder_id:
                    return {"id": rule["id"], "created": False, "updated": False}
                actions["moveToFolder"] = dest_folder_id
                actions["stopProcessingRules"] = True
                update_resp = requests.patch(
                    f"{rules_url}/{rule['id']}",
                    headers=headers,
                    json={"actions": actions},
                    timeout=15,
                )
                update_resp.raise_for_status()
                return {"id": rule["id"], "created": False, "updated": True}

    body = {
        "displayName": display_name,
        "sequence": len(existing_rules) + 1,
        "isEnabled": True,
        "conditions": {"senderContains": [domain]},
        "actions": {
            "moveToFolder": dest_folder_id,
            "stopProcessingRules": True,
        },
    }
    create_resp = requests.post(rules_url, headers=headers, json=body, timeout=15)
    create_resp.raise_for_status()
    return {"id": create_resp.json()["id"], "created": True, "updated": False}


def organize_sender(
    account_id: str,
    folder_key: str,
    sender_address: str,
    folder_name: str,
    create_rule: bool = False,
) -> dict:
    """Create (or reuse) a folder under Mail Box and move this sender's messages into it.

    If sender_address is blank, this is a message with no return address at all --
    every other no-return-address message in the folder is grouped and moved
    alongside it (folder_name is expected to already be the model-suggested name
    from count_sender_messages).

    If create_rule is set, also create (or reuse) an Inbox rule so future mail from
    this sender is moved into the same folder automatically. Rule creation is skipped
    for the no-return-address group since there's no sender domain for the rule to match.
    """
    headers = get_headers(account_id)
    if not headers:
        return {"error": "Not authenticated."}

    clean_name = sanitize_folder_name(folder_name)
    folder = _ORGANIZER_FOLDERS.get(folder_key, "inbox")

    # The folder-create + move is the part that must succeed for this call to count as
    # successful at all -- if it blows up, nothing happened and returning an error is correct.
    try:
        structure = _sync_mailbox_structure(headers)
        folder_info = _find_or_create_folder(headers, clean_name, structure)
        message_ids = _fetch_sender_message_ids(headers, folder, sender_address, MAX_MOVE_PER_ACTION + 1)
        truncated = len(message_ids) > MAX_MOVE_PER_ACTION
        message_ids = message_ids[:MAX_MOVE_PER_ACTION]
        moved = _batch_move(headers, message_ids, folder_info["id"]) if message_ids else 0
    except Exception as exc:
        log.error("Organize failed for %s: %s", account_id, exc)
        return {"error": str(exc)}

    # The rule step is best-effort on top of an already-successful move -- a failure here
    # (e.g. missing MailboxSettings.ReadWrite permission) must not report the move as failed.
    rule_created = None
    rule_already_existed = None
    rule_error = None
    if create_rule:
        if not sender_address:
            rule_error = "Cannot create a sender rule for messages with no return address."
        else:
            try:
                rule_info = _find_or_create_rule(
                    headers, sender_address, folder_info["id"], f"MyHomeDash: {clean_name}"
                )
                rule_created = rule_info["created"]
                rule_already_existed = not rule_info["created"]
            except Exception as exc:
                log.error("Rule creation failed for %s: %s", account_id, exc)
                rule_error = str(exc)

    return {
        "folder_name": clean_name,
        "folder_path": folder_info["path"],
        "folder_created": folder_info["created"],
        "moved": moved,
        "truncated": truncated,
        "no_return_address": not sender_address,
        "rule_created": rule_created,
        "rule_already_existed": rule_already_existed,
        "rule_error": rule_error,
    }


# ── Public ────────────────────────────────────────────────────────────────────

def fetch() -> dict:
    """Return email summaries for all configured accounts."""
    cfg = get_config()
    email_cfg = cfg.get("email", {})
    max_subjects = email_cfg.get("max_subjects_per_account", 10)
    accounts_cfg = email_cfg.get("accounts", [])

    account_results = []
    for acc in accounts_cfg:
        acc_id = acc.get("id", "")
        label = acc.get("label", acc_id)
        acc_type = acc.get("type", "")

        if acc_type == "microsoft":
            # Derive the MSAL account_id from the config id
            msal_id = {"work_outlook": "work_outlook", "home_outlook": "home_outlook"}.get(acc_id, acc_id)
            account_results.append(_fetch_microsoft_email(msal_id, label, max_subjects))
        elif acc_type == "google":
            account_results.append(_fetch_gmail(acc_id, label, max_subjects))
        else:
            account_results.append({"id": acc_id, "label": label, "error": f"Unknown type: {acc_type}"})

    total_unread = sum(
        a.get("unread_count", 0) for a in account_results if not a.get("error")
    )
    return {"accounts": account_results, "total_unread": total_unread}
