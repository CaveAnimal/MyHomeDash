"""Standalone Playwright script launched as a subprocess by spam_filer.

Reads task from --task JSON file, writes status to --status JSON file,
watches --continue flag file for CAPTCHA signals.
"""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _write_status(status_file: Path, data: dict):
    status_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _build_report_text(rec: dict) -> str:
    lines = [
        f"Unwanted call from {rec['display']}.",
        f"Type: {rec.get('call_type', 'other')}.",
    ]
    if rec.get("when"):
        lines.append(f"Date/time: {rec['when']}.")
    lines.append("I did not give this caller permission to contact me.")
    if rec.get("notes"):
        lines.append(f"Details: {rec['notes']}")
    return " ".join(lines)


async def _wait_for_continue(continue_file: Path):
    """Poll for the continue flag file."""
    while True:
        if continue_file.exists():
            continue_file.unlink(missing_ok=True)
            return
        await asyncio.sleep(0.5)


async def _file_ftc(page, rec, status, status_file, continue_file):
    s = status["sites"]["ftc"]
    s["status"] = "launching"
    s["step"] = "FTC ➜ Opening ReportFraud"
    s["started_at"] = _now()
    _write_status(status_file, status)

    await page.goto("https://reportfraud.ftc.gov/", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    s["status"] = "filling"
    s["step"] = "FTC ➜ Starting report"
    _write_status(status_file, status)
    try:
        btn = page.get_by_role("link", name="Report Now")
        if await btn.count() > 0:
            await btn.first.click()
            await page.wait_for_timeout(2000)
    except Exception:
        pass

    s["step"] = "FTC ➜ Selecting complaint type"
    _write_status(status_file, status)
    try:
        opt = page.get_by_text("Unwanted Calls", exact=False)
        if await opt.count() > 0:
            await opt.first.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass

    s["step"] = "FTC ➜ Filling phone number"
    _write_status(status_file, status)
    report_text = _build_report_text(rec)
    try:
        inp = page.locator('input[type="tel"], input[name*="phone"], input[id*="phone"]').first
        if await inp.count() > 0:
            await inp.fill(rec["display"])
    except Exception:
        pass

    s["step"] = "FTC ➜ Filling details"
    _write_status(status_file, status)
    try:
        ta = page.locator("textarea").first
        if await ta.count() > 0:
            await ta.fill(report_text)
    except Exception:
        pass

    s["status"] = "waiting-captcha"
    s["step"] = "FTC ➜ Solve the CAPTCHA, then click Continue"
    _write_status(status_file, status)
    await _wait_for_continue(continue_file)

    s["status"] = "done"
    s["step"] = "FTC ➜ Complete"
    s["finished_at"] = _now()
    _write_status(status_file, status)


async def _file_fcc(page, rec, status, status_file, continue_file):
    s = status["sites"]["fcc"]
    s["status"] = "launching"
    s["step"] = "FCC ➜ Opening Consumer Complaints"
    s["started_at"] = _now()
    _write_status(status_file, status)

    await page.goto("https://consumercomplaints.fcc.gov/hc/en-us", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    s["status"] = "filling"
    s["step"] = "FCC ➜ Navigating to phone complaint"
    _write_status(status_file, status)
    try:
        lnk = page.get_by_role("link", name="Phone")
        if await lnk.count() > 0:
            await lnk.first.click()
            await page.wait_for_timeout(2000)
    except Exception:
        pass

    try:
        lnk = page.get_by_role("link", name="Unwanted Calls")
        if await lnk.count() > 0:
            await lnk.first.click()
            await page.wait_for_timeout(2000)
    except Exception:
        pass

    try:
        lnk = page.get_by_role("link", name="File a Complaint")
        if await lnk.count() > 0:
            await lnk.first.click()
            await page.wait_for_timeout(2000)
    except Exception:
        pass

    s["step"] = "FCC ➜ Filling phone number"
    _write_status(status_file, status)
    report_text = _build_report_text(rec)
    try:
        inp = page.locator('input[type="tel"], input[name*="phone"], input[id*="phone"], input[placeholder*="phone" i]').first
        if await inp.count() > 0:
            await inp.fill(rec["display"])
    except Exception:
        pass

    s["step"] = "FCC ➜ Filling description"
    _write_status(status_file, status)
    try:
        ta = page.locator("textarea").first
        if await ta.count() > 0:
            await ta.fill(report_text)
    except Exception:
        pass

    s["status"] = "waiting-captcha"
    s["step"] = "FCC ➜ Solve the CAPTCHA, then click Continue"
    _write_status(status_file, status)
    await _wait_for_continue(continue_file)

    s["status"] = "done"
    s["step"] = "FCC ➜ Complete"
    s["finished_at"] = _now()
    _write_status(status_file, status)


async def _file_bbb(page, rec, status, status_file, continue_file):
    s = status["sites"]["bbb"]
    s["status"] = "launching"
    s["step"] = "BBB ➜ Opening Scam Tracker"
    s["started_at"] = _now()
    _write_status(status_file, status)

    await page.goto("https://www.bbb.org/scamtracker/reportscam", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    s["status"] = "filling"
    s["step"] = "BBB ➜ Filling scam type"
    _write_status(status_file, status)
    try:
        sel = page.locator('select, [role="listbox"]').first
        if await sel.count() > 0:
            await sel.select_option(label="Phone Call")
    except Exception:
        pass

    s["step"] = "BBB ➜ Filling phone number"
    _write_status(status_file, status)
    try:
        inp = page.locator('input[type="tel"], input[name*="phone"], input[id*="phone"]').first
        if await inp.count() > 0:
            await inp.fill(rec["display"])
    except Exception:
        pass

    s["step"] = "BBB ➜ Filling description"
    _write_status(status_file, status)
    report_text = _build_report_text(rec)
    try:
        ta = page.locator("textarea").first
        if await ta.count() > 0:
            await ta.fill(report_text)
    except Exception:
        pass

    s["status"] = "waiting-captcha"
    s["step"] = "BBB ➜ Solve the CAPTCHA, then click Continue"
    _write_status(status_file, status)
    await _wait_for_continue(continue_file)

    s["status"] = "done"
    s["step"] = "BBB ➜ Complete"
    s["finished_at"] = _now()
    _write_status(status_file, status)


HANDLERS = {"ftc": _file_ftc, "fcc": _file_fcc, "bbb": _file_bbb}


async def main(task_file: Path, status_file: Path, continue_file: Path):
    task = json.loads(task_file.read_text(encoding="utf-8"))
    records = task["records"]
    site_ids = task["site_ids"]

    status = {
        "active": True,
        "batch_id": task.get("batch_id", ""),
        "crash_error": "",
        "sites": {sid: {"site_id": sid, "site_name": sid.upper(), "status": "idle", "step": "", "error": "", "started_at": None, "finished_at": None} for sid in site_ids},
    }
    _write_status(status_file, status)

    from playwright.async_api import async_playwright
    try:
        import os, glob
        candidates = [
            os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""),
            r"C:\Users\jpful\AppData\Local\ms-playwright",
            str(Path.home() / "AppData" / "Local" / "ms-playwright"),
        ]
        chrome_exe = None
        for bp in candidates:
            if not bp:
                continue
            matches = glob.glob(os.path.join(bp, "chromium-*", "chrome-win64", "chrome.exe"))
            if matches:
                chrome_exe = matches[0]
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = bp
                break

        async with async_playwright() as pw:
            launch_opts = {"headless": False}
            if chrome_exe:
                launch_opts["executable_path"] = chrome_exe
            browser = await pw.chromium.launch(**launch_opts)
            context = await browser.new_context(viewport={"width": 1200, "height": 900})

            for site_id in site_ids:
                handler = HANDLERS.get(site_id)
                if not handler:
                    continue
                for rec in records:
                    page = await context.new_page()
                    try:
                        await handler(page, rec, status, status_file, continue_file)
                    except Exception as exc:
                        status["sites"][site_id]["status"] = "error"
                        status["sites"][site_id]["error"] = str(exc)
                        status["sites"][site_id]["finished_at"] = _now()
                        _write_status(status_file, status)

            await asyncio.sleep(2)
            await browser.close()
    except Exception as exc:
        import traceback
        status["crash_error"] = traceback.format_exc()
    finally:
        status["active"] = False
        _write_status(status_file, status)


if __name__ == "__main__":
    task_file = Path(sys.argv[1])
    status_file = Path(sys.argv[2])
    continue_file = Path(sys.argv[3])
    asyncio.run(main(task_file, status_file, continue_file))
