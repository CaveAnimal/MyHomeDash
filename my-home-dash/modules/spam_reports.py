"""Spam phone number queue, report packets, and reporting history.

The FTC, FCC and most other reporting sites only accept reports through
CAPTCHA-protected web forms (no public submission API), so this module does not
auto-submit. Numbers are added to a queue one at a time; "processing" the queue
freezes it into a batch with ready-to-paste report text and destination links;
the user then checks off each destination as they file it, and each check is
timestamped in the history.
"""
import json
import re
import threading
from datetime import datetime
from pathlib import Path

_STORE = Path(__file__).resolve().parent.parent / "data" / "spam_reports.json"
_LOCK = threading.Lock()

CALL_TYPES = {
    "robocall": "Robocall / prerecorded message",
    "live": "Live caller",
    "text": "Spam text message",
    "scam": "Scam / fraud attempt",
    "other": "Other unwanted call",
}


class DuplicateNumber(Exception):
    def __init__(self, record: dict):
        super().__init__("Duplicate number")
        self.record = record


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_phone(raw: str):
    """Return (e164, display) for a US/NANP number, or None if invalid."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] in "01" or digits[3] in "01":
        return None
    return f"+1{digits}", f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def _destinations(digits: str):
    return [
        {"id": "ftc", "name": "FTC (Do Not Call / ReportFraud)",
         "url": "https://reportfraud.ftc.gov/",
         "note": "Choose 'Unwanted calls' and paste the number. Feeds the law-enforcement database used by carriers and call-blocking apps."},
        {"id": "fcc", "name": "FCC Consumer Complaints",
         "url": "https://consumercomplaints.fcc.gov/",
         "note": "File under 'Phone > Unwanted calls'. FCC uses reports to pursue robocallers and carriers."},
        {"id": "bbb", "name": "BBB Scam Tracker",
         "url": "https://www.bbb.org/scamtracker/reportscam",
         "note": "Public database that warns other consumers; best when the call was a scam."},
        {"id": "ic3", "name": "FBI IC3 (scams / money lost)",
         "url": "https://www.ic3.gov/",
         "note": "Only if the caller tried to defraud you or you lost money."},
        {"id": "800notes", "name": "800notes (public lookup)",
         "url": f"https://800notes.com/Phone.aspx/1-{digits[:3]}-{digits[3:6]}-{digits[6:]}",
         "note": "Leave a comment so others searching this number see it."},
        {"id": "carrier", "name": "Your carrier",
         "url": "",
         "note": "Forward spam texts to 7726 (SPAM). For calls, use your carrier's app (AT&T ActiveArmor, Verizon Call Filter, T-Mobile Scam Shield)."},
        {"id": "phone", "name": "Block on your phone",
         "url": "",
         "note": "Block and report as spam in the phone app so the on-device filter learns it."},
    ]


def build_report_text(rec: dict) -> str:
    lines = [
        f"Unwanted call from {rec['display']}.",
        f"Type: {CALL_TYPES.get(rec['call_type'], CALL_TYPES['other'])}.",
    ]
    if rec.get("when"):
        lines.append(f"Date/time: {rec['when']}.")
    lines.append("I did not give this caller permission to contact me.")
    if rec.get("notes"):
        lines.append(f"Details: {rec['notes']}")
    return " ".join(lines)


def _load() -> list:
    try:
        return json.loads(_STORE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []


def _save(items: list) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    _STORE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _hydrate(rec: dict) -> dict:
    out = dict(rec)
    done = rec.get("done", {})
    out["destinations"] = [
        {**d, "done_at": done.get(d["id"])} for d in _destinations(rec["e164"][2:])
    ]
    out["reported_to"] = [d["name"] for d in out["destinations"] if d["done_at"]]
    out["report_text"] = build_report_text(rec)
    return out


def snapshot() -> dict:
    """Queue (oldest first), history (newest batch first), and the latest batch."""
    with _LOCK:
        items = [_hydrate(i) for i in _load()]
    queued = [i for i in items if i["status"] == "queued"]
    history = sorted((i for i in items if i["status"] != "queued"),
                     key=lambda i: i["processed_at"], reverse=True)
    return {"queued": queued, "history": history, "call_types": CALL_TYPES}


def add_number(raw: str, call_type: str = "robocall", when: str = "", notes: str = "") -> dict:
    parsed = normalize_phone(raw)
    if not parsed:
        raise ValueError("Enter a valid 10-digit US/Canada phone number.")
    e164, display = parsed
    with _LOCK:
        items = _load()
        existing = next((i for i in items if i["e164"] == e164), None)
        if existing:
            existing.setdefault("dup_attempts", []).append(_now())
            _save(items)
            raise DuplicateNumber(_hydrate(existing))
        rec = {
            "e164": e164, "display": display,
            "call_type": call_type if call_type in CALL_TYPES else "other",
            "when": when.strip()[:80], "notes": notes.strip()[:500],
            "status": "queued", "added": _now(), "done": {}, "dup_attempts": [],
        }
        items.append(rec)
        _save(items)
        return _hydrate(rec)


def remove_queued(e164: str) -> None:
    with _LOCK:
        items = _load()
        kept = [i for i in items if not (i["e164"] == e164 and i["status"] == "queued")]
        if len(kept) == len(items):
            raise KeyError("That number is not in the queue.")
        _save(kept)


def process_queue() -> dict:
    """Freeze every queued number into one batch and return its report packet."""
    with _LOCK:
        items = _load()
        queued = [i for i in items if i["status"] == "queued"]
        if not queued:
            raise ValueError("The queue is empty.")
        stamp = _now()
        batch_id = stamp.replace("-", "").replace(":", "").replace("T", "-")
        for rec in queued:
            rec.update(status="processed", batch_id=batch_id, processed_at=stamp)
        _save(items)
        hydrated = [_hydrate(r) for r in queued]
    packet = "\n".join(f"{i + 1}. {r['report_text']}" for i, r in enumerate(hydrated))
    return {"batch_id": batch_id, "processed_at": stamp, "numbers": hydrated, "packet_text": packet}


def set_done(e164: str, dest_id: str, done: bool) -> dict:
    with _LOCK:
        items = _load()
        rec = next((i for i in items if i["e164"] == e164 and i["status"] != "queued"), None)
        if not rec:
            raise KeyError("Unknown or unprocessed number.")
        if dest_id not in {d["id"] for d in _destinations(e164[2:])}:
            raise KeyError("Unknown destination.")
        if done:
            rec["done"][dest_id] = _now()
        else:
            rec["done"].pop(dest_id, None)
        _save(items)
        return _hydrate(rec)
