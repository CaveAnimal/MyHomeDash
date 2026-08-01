"""
APScheduler job definitions for My Home Dash.

Jobs:
  - morning_brief: Runs at configured time (default 7:30 AM) — all modules
  - intraday_update: Every N minutes between start/end times — email, calendar, teams, github
  - Both jobs respect is_workday() before executing
"""

import logging
from datetime import datetime

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config_loader import get_config, get_enabled_dashboard_sections
from modules.holidays_mod import is_workday

log = logging.getLogger(__name__)

# Modules that run on every intra-day update
INTRADAY_MODULES = ["email", "calendar", "teams", "github"]

# All modules for morning brief
ALL_MODULES = ["weather", "news", "calendar", "email", "github", "teams"]


def _get_all_modules() -> list[str]:
    enabled_sections = set(get_enabled_dashboard_sections())
    return [name for name in ALL_MODULES if name in enabled_sections]


def _get_intraday_modules() -> list[str]:
    enabled_sections = set(get_enabled_dashboard_sections())
    return [name for name in INTRADAY_MODULES if name in enabled_sections]


def _safe_fetch(module_name: str) -> dict:
    """Import and run a module's fetch(), returning its result or an error dict."""
    module_map = {
        "calendar": "modules.calendar_mod",
        "email":    "modules.email_mod",
        "github":   "modules.github_mod",
        "teams":    "modules.teams_mod",
        "weather":  "modules.weather_mod",
        "news":     "modules.news_mod",
    }
    mod_path = module_map.get(module_name)
    if not mod_path:
        return {"error": f"Unknown module: {module_name}"}
    try:
        import importlib
        mod = importlib.import_module(mod_path)
        return mod.fetch()
    except Exception as exc:
        log.error("Module %s raised: %s", module_name, exc, exc_info=True)
        return {"error": str(exc)}


def run_module(module_name: str, cache: dict) -> None:
    """Fetch a single module and update the cache."""
    log.info("Fetching module: %s", module_name)
    cache[module_name] = _safe_fetch(module_name)


def run_all_modules(cache: dict) -> None:
    """Fetch all modules and update the cache."""
    for name in _get_all_modules():
        run_module(name, cache)
    cache["last_full_refresh"] = datetime.now()
    log.info("Full refresh complete.")


def _run_morning_brief(cache: dict) -> None:
    if not is_workday():
        log.info("Skipping morning brief — not a workday.")
        return
    log.info("Running morning brief…")
    run_all_modules(cache)


def _run_intraday(cache: dict) -> None:
    cfg = get_config()
    tz_name = cfg.get("timezone", "America/New_York")
    user_tz = pytz.timezone(tz_name)
    now = datetime.now(tz=user_tz)

    if not is_workday(now.date()):
        log.debug("Skipping intra-day — not a workday.")
        return

    sched = cfg.get("schedule", {})
    start_str = sched.get("intraday_start", "09:00")
    end_str = sched.get("intraday_end", "18:00")

    start_h, start_m = (int(x) for x in start_str.split(":"))
    end_h, end_m = (int(x) for x in end_str.split(":"))

    now_minutes = now.hour * 60 + now.minute
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m

    if not (start_minutes <= now_minutes <= end_minutes):
        log.debug("Skipping intra-day — outside active window (%s–%s).", start_str, end_str)
        return

    intraday_modules = _get_intraday_modules()
    if not intraday_modules:
        log.info("Skipping intra-day update — no enabled sections use intra-day refresh.")
        return

    log.info("Running intra-day update…")
    for name in intraday_modules:
        run_module(name, cache)
    cache["last_intraday"] = datetime.now()


def init_scheduler(app, cache: dict) -> None:
    """Create and start the APScheduler with morning + intraday jobs."""
    cfg = get_config()
    sched_cfg = cfg.get("schedule", {})
    tz_name = cfg.get("timezone", "America/New_York")

    morning_time = sched_cfg.get("morning_brief_time", "07:30")
    morning_h, morning_m = morning_time.split(":")

    interval_minutes = sched_cfg.get("intraday_interval_minutes", 90)

    scheduler = BackgroundScheduler(timezone=tz_name)

    # Morning brief job — cron trigger at configured time
    scheduler.add_job(
        func=lambda: _run_morning_brief(cache),
        trigger=CronTrigger(hour=morning_h, minute=morning_m, timezone=tz_name),
        id="morning_brief",
        name="Morning Brief",
        replace_existing=True,
    )

    # Intra-day job — interval trigger (window check is inside the job)
    scheduler.add_job(
        func=lambda: _run_intraday(cache),
        trigger=IntervalTrigger(minutes=interval_minutes, timezone=tz_name),
        id="intraday_update",
        name="Intra-day Update",
        replace_existing=True,
    )

    scheduler.start()
    log.info(
        "Scheduler started. Morning brief at %s, intra-day every %d min.",
        morning_time, interval_minutes,
    )

    # Shut down gracefully with the app
    import atexit
    atexit.register(lambda: scheduler.shutdown(wait=False))
