"""
Read-only audit: which messages in Home Outlook's "Mail Box" folders were
originally delivered to Junk?

Background: the Email organizer used to allow moving mail out of Junk. Graph
doesn't record a message's previous folder, but Outlook stamps its delivery
verdict into the X-Microsoft-Antispam-Mailbox-Delivery header, which survives
moves:
    dest:J + OFR:SpamFilter*  -> junk_spam_filter   (Outlook's spam filter sent it to Junk)
    dest:J + any other OFR    -> junk_your_settings (your junk settings/blocked senders sent
                                                     it to Junk; may have been rescued by hand)
    dest:I                    -> inbox
    header missing            -> unknown

The header reflects where mail was *delivered*, not where it sat when the
organizer moved it -- mail you hand-rescued from Junk to Inbox still reads dest:J.

Nothing is moved or changed. Run from my-home-dash/:
    venv\\Scripts\\python.exe scripts\\junk_move_audit.py [--since 2026-09-01]

Writes data/junk_move_audit.csv (gitignored) and prints a per-folder summary.
"""

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from auth.microsoft_client import get_headers  # noqa: E402
from modules.email_mod import GRAPH_BASE, _sync_mailbox_structure  # noqa: E402

OUT_PATH = ROOT / "data" / "junk_move_audit.csv"
DELIVERY_HEADER = "x-microsoft-antispam-mailbox-delivery"
_DEST_RE = re.compile(r"(?:^|;)dest:(\w)", re.I)
_OFR_RE = re.compile(r"(?:^|;)OFR:([^;]+)", re.I)


def classify(delivery: str) -> tuple[str, str, str]:
    dest = _DEST_RE.search(delivery or "")
    ofr = _OFR_RE.search(delivery or "")
    dest_v = dest.group(1).upper() if dest else ""
    ofr_v = ofr.group(1) if ofr else ""
    if dest_v == "J":
        verdict = "junk_spam_filter" if ofr_v.lower().startswith("spamfilter") else "junk_your_settings"
    elif dest_v == "I":
        verdict = "inbox"
    else:
        verdict = "unknown"
    return verdict, dest_v, ofr_v


def iter_messages(headers: dict, folder_id: str, since: str | None):
    url = (
        f"{GRAPH_BASE}/me/mailFolders/{folder_id}/messages"
        "?$select=subject,from,receivedDateTime,lastModifiedDateTime,internetMessageHeaders"
        "&$top=50"
    )
    if since:
        url += f"&$filter=lastModifiedDateTime ge {since}T00:00:00Z"
    while url:
        resp = requests.get(url, headers=headers, timeout=60)
        resp.raise_for_status()
        body = resp.json()
        yield from body.get("value", [])
        url = body.get("@odata.nextLink")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", help="Only messages last modified (i.e. moved) on/after YYYY-MM-DD")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    headers = get_headers("home_outlook")
    if not headers:
        sys.exit("Not authenticated. Run auth/setup_microsoft_home.py")

    structure = _sync_mailbox_structure(headers)
    folders = [f for f in structure["folders"] if f["path"].casefold().startswith("mail box/")]
    print(f"Scanning {len(folders)} folders under Mail Box...")

    rows = []
    per_folder: dict[str, Counter] = defaultdict(Counter)
    for i, folder in enumerate(folders, 1):
        try:
            for m in iter_messages(headers, folder["id"], args.since):
                hdrs = {h["name"].lower(): h["value"] for h in m.get("internetMessageHeaders") or []}
                verdict, dest, ofr = classify(hdrs.get(DELIVERY_HEADER, ""))
                addr = (m.get("from") or {}).get("emailAddress") or {}
                rows.append({
                    "verdict": verdict,
                    "folder": folder["path"],
                    "received": m.get("receivedDateTime", ""),
                    "last_modified": m.get("lastModifiedDateTime", ""),
                    "from_name": addr.get("name", ""),
                    "from_address": addr.get("address", ""),
                    "subject": m.get("subject") or "",
                    "dest": dest,
                    "ofr": ofr,
                    "message_id": m.get("id", ""),
                })
                per_folder[folder["path"]][verdict] += 1
        except requests.RequestException as exc:
            print(f"  ! {folder['path']}: {exc}")
        if i % 25 == 0:
            print(f"  {i}/{len(folders)} folders, {len(rows)} messages so far")

    order = {"junk_spam_filter": 0, "junk_your_settings": 1, "unknown": 2, "inbox": 3}
    rows.sort(key=lambda r: (order[r["verdict"]], r["folder"], r["received"]))
    OUT_PATH.parent.mkdir(exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["verdict"])
        writer.writeheader()
        writer.writerows(rows)

    # Organizer-created Inbox rules, with the verdict mix of the folder each one targets.
    rule_lines = []
    try:
        resp = requests.get(f"{GRAPH_BASE}/me/mailFolders/inbox/messageRules", headers=headers, timeout=30)
        resp.raise_for_status()
        by_id = {f["id"]: f["path"] for f in structure["folders"]}
        for rule in resp.json().get("value", []):
            if not (rule.get("displayName") or "").startswith("MyHomeDash:"):
                continue
            dest_id = (rule.get("actions") or {}).get("moveToFolder", "")
            path = by_id.get(dest_id, "?")
            mix = per_folder.get(path, Counter())
            rule_lines.append(f"  {rule['displayName']} -> {path}  [{dict(mix)}]")
    except requests.RequestException as exc:
        rule_lines.append(f"  ! could not list rules: {exc}")

    totals = Counter(r["verdict"] for r in rows)
    print(f"\nTotal messages: {len(rows)}  {dict(totals)}")
    print("\nFolders containing mail delivered to Junk:")
    for path, mix in sorted(per_folder.items(), key=lambda kv: -(kv[1]["junk_spam_filter"] + kv[1]["junk_your_settings"])):
        junk = mix["junk_spam_filter"] + mix["junk_your_settings"]
        if junk:
            print(f"  {junk:4d} junk / {sum(mix.values()):4d} total  {path}  {dict(mix)}")
    print("\nMyHomeDash Inbox rules:")
    print("\n".join(rule_lines) or "  (none)")
    print(f"\nCSV written to {OUT_PATH}")


if __name__ == "__main__":
    main()
