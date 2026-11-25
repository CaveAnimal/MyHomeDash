"""Spam report filing orchestrator.

Writes a task file, then launches run_spam_filer.bat via os.startfile so
the Playwright browser opens in the user's desktop session (not session 0).
Communication is via JSON files:
  - task.json: input records and site list
  - status.json: live progress (polled by the dashboard)
  - continue.flag: touched by the dashboard to signal CAPTCHA solved
"""

import json
import os
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "filer"
_TASK_FILE = _DATA_DIR / "task.json"
_STATUS_FILE = _DATA_DIR / "status.json"
_CONTINUE_FILE = _DATA_DIR / "continue.flag"
_BAT_FILE = Path(__file__).resolve().parent.parent / "scripts" / "run_spam_filer.bat"


def current_session() -> dict | None:
    try:
        return json.loads(_STATUS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def signal_continue():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _CONTINUE_FILE.write_text("go", encoding="utf-8")


def start_filing(records: list, site_ids: list, batch_id: str) -> dict:
    # Check if already running
    session = current_session()
    if session and session.get("active"):
        raise RuntimeError("A filing session is already running.")

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _CONTINUE_FILE.unlink(missing_ok=True)

    task = {"records": records, "site_ids": site_ids, "batch_id": batch_id}
    _TASK_FILE.write_text(json.dumps(task, indent=2), encoding="utf-8")

    initial = {
        "active": True,
        "batch_id": batch_id,
        "crash_error": "",
        "sites": {sid: {"site_id": sid, "site_name": sid.upper(), "status": "idle", "step": "", "error": "", "started_at": None, "finished_at": None} for sid in site_ids},
    }
    _STATUS_FILE.write_text(json.dumps(initial, indent=2), encoding="utf-8")

    os.startfile(str(_BAT_FILE))

    return initial
