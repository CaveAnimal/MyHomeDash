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
import logging
import os
import re
from email import message_from_bytes
from email.header import decode_header
from email.utils import parsedate_to_datetime

import requests

from auth.microsoft_client import get_headers
from auth.google_client import get_gmail_service
from config_loader import get_config

log = logging.getLogger(__name__)
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_GMAIL_ENV_PREFIX = {"gmail_1": "GMAIL_1", "gmail_2": "GMAIL_2"}

# ── Home Outlook folder organizer (Inbox / Junk only, for now) ─────────────────
# Separate from the read-only unread-summary path above: this talks to Graph
# on demand (not on the scheduler's cache cycle) so folder switches and moves
# reflect the mailbox in real time.

_ORGANIZER_FOLDERS = {"inbox": "inbox", "junk": "junkemail"}
_FOLDER_NAME_STRIP_RE = re.compile(r'[\\/:*?"<>|#]')
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
            subjects.append({
                "subject": m.get("subject", "(No subject)"),
                "from": sender,
                "received": m.get("receivedDateTime", "")[:16].replace("T", " "),
            })

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
            subjects.append({
                "subject": _decode_mime_words(parsed.get("Subject", "")) or "(No subject)",
                "from": _decode_mime_words(parsed.get("From", "")) or "Unknown",
                "received": received,
            })

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
                subjects.append({
                    "subject": headers.get("Subject", "(No subject)"),
                    "from": headers.get("From", "Unknown"),
                    "received": date_str,
                })
            except Exception as inner:
                log.debug("Skipping Gmail message: %s", inner)

        return {"id": account_id, "label": label, "type": "google",
                "unread_count": unread_count, "subjects": subjects}

    except Exception as exc:
        log.error("Gmail fetch failed for %s: %s", account_id, exc)
        return {"id": account_id, "label": label, "type": "google", "error": str(exc)}


def sanitize_folder_name(raw: str, fallback: str = "Sorted Mail") -> str:
    """Strip characters Outlook rejects in folder names and cap the length."""
    cleaned = _FOLDER_NAME_STRIP_RE.sub("", raw or "").strip()
    return (cleaned or fallback)[:50]


def list_folder_messages(account_id: str, folder_key: str, max_items: int = 20) -> dict:
    """Recent messages (read or unread) from Inbox or Junk, for the folder-organizer UI."""
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


def count_sender_messages(account_id: str, folder_key: str, sender_address: str) -> dict:
    """Total messages sharing this sender's base domain in the given folder."""
    headers = get_headers(account_id)
    if not headers:
        return {"error": "Not authenticated."}
    if not sender_address:
        return {"error": "Missing sender address."}

    folder = _ORGANIZER_FOLDERS.get(folder_key, "inbox")
    domain = _base_domain(sender_address)
    try:
        entries = _fetch_folder_from_addresses(headers, folder)
        count = sum(1 for _msg_id, addr in entries if _base_domain(addr) == domain)
        return {"count": count}
    except Exception as exc:
        log.error("Sender count failed for %s: %s", account_id, exc)
        return {"error": str(exc)}


def _find_or_create_folder(headers: dict, display_name: str) -> dict:
    """Look up a top-level mail folder by name, creating it if it doesn't exist yet.

    Reusing an existing folder makes "organize this sender" idempotent — checking
    the same sender again later just adds newer mail to the same folder.
    """
    safe_name = display_name.replace("'", "''")
    resp = requests.get(
        f"{GRAPH_BASE}/me/mailFolders",
        headers=headers,
        params={"$filter": f"displayName eq '{safe_name}'"},
        timeout=15,
    )
    resp.raise_for_status()
    existing = resp.json().get("value", [])
    if existing:
        return {"id": existing[0]["id"], "created": False}

    create_resp = requests.post(
        f"{GRAPH_BASE}/me/mailFolders",
        headers=headers,
        json={"displayName": display_name},
        timeout=15,
    )
    create_resp.raise_for_status()
    return {"id": create_resp.json()["id"], "created": True}


def _fetch_sender_message_ids(headers: dict, folder: str, sender_address: str, limit: int) -> list[str]:
    domain = _base_domain(sender_address)
    entries = _fetch_folder_from_addresses(headers, folder)
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
                return {"id": rule["id"], "created": False}

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
    return {"id": create_resp.json()["id"], "created": True}


def organize_sender(
    account_id: str,
    folder_key: str,
    sender_address: str,
    folder_name: str,
    create_rule: bool = False,
) -> dict:
    """Create (or reuse) a top-level folder and move every message from this sender into it.

    If create_rule is set, also create (or reuse) an Inbox rule so future mail from
    this sender is moved into the same folder automatically.
    """
    headers = get_headers(account_id)
    if not headers:
        return {"error": "Not authenticated."}
    if not sender_address:
        return {"error": "Missing sender address."}

    clean_name = sanitize_folder_name(folder_name)
    folder = _ORGANIZER_FOLDERS.get(folder_key, "inbox")

    # The folder-create + move is the part that must succeed for this call to count as
    # successful at all -- if it blows up, nothing happened and returning an error is correct.
    try:
        folder_info = _find_or_create_folder(headers, clean_name)
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
        "folder_created": folder_info["created"],
        "moved": moved,
        "truncated": truncated,
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
