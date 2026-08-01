"""
Holidays module — checks whether a given date is a public holiday.
Uses the free Nager.Date API (https://date.nager.at).
No API key required.
"""

import logging
from datetime import date

import requests

from config_loader import get_config

log = logging.getLogger(__name__)
_BASE_URL = "https://date.nager.at/api/v3"


def get_holidays(year: int, country_code: str | None = None) -> list[str]:
    """
    Return a list of holiday date strings (YYYY-MM-DD) for the given year/country.
    Returns empty list on failure.
    """
    cfg = get_config()
    country = country_code or cfg.get("schedule", {}).get("holiday_country", "US")
    url = f"{_BASE_URL}/PublicHolidays/{year}/{country}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return [h["date"] for h in resp.json()]
    except Exception as exc:
        log.error("Failed to fetch holidays: %s", exc)
        return []


def is_holiday(check_date: date | None = None, country_code: str | None = None) -> bool:
    """Return True if check_date (defaults to today) is a public holiday."""
    if check_date is None:
        check_date = date.today()
    date_str = check_date.strftime("%Y-%m-%d")
    holidays = get_holidays(check_date.year, country_code)
    return date_str in holidays


def is_workday(check_date: date | None = None) -> bool:
    """Return True if check_date is a weekday and NOT a holiday."""
    if check_date is None:
        check_date = date.today()
    cfg = get_config()
    run_days = cfg.get("schedule", {}).get("run_days", [0, 1, 2, 3, 4])
    if check_date.weekday() not in run_days:
        return False
    return not is_holiday(check_date)
