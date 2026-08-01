"""
Calendar module — fetches today's events either from a published ICS feed
(CALENDAR_ICS_URL, no OAuth required) or from the work Outlook calendar via
Microsoft Graph API. The ICS feed is used automatically whenever
CALENDAR_ICS_URL is set; otherwise this falls back to the original Graph path.
"""

import logging
import os
import re
from datetime import date, datetime, timedelta

import pytz
import requests
from icalendar import Calendar
import recurring_ical_events

from auth.microsoft_client import get_headers
from config_loader import get_config

log = logging.getLogger(__name__)
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_URL_PATTERN = re.compile(r"https?://\S+")


def _parse_dt(dt_str: str, tz_str: str, user_tz) -> str:
    """Parse a Graph API dateTime + timeZone pair into a local time string."""
    try:
        tz = pytz.timezone(tz_str) if tz_str else pytz.utc
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = tz.localize(dt)
        local_dt = dt.astimezone(user_tz)
        return local_dt.strftime("%I:%M %p").lstrip("0")
    except Exception:
        return dt_str[:16]


def _format_local_time(dt: datetime, user_tz) -> str:
    return dt.astimezone(user_tz).strftime("%I:%M %p").lstrip("0")


def _ics_attendee_names(component) -> list[str]:
    raw_attendees = component.get("ATTENDEE")
    if raw_attendees is None:
        return []
    if not isinstance(raw_attendees, list):
        raw_attendees = [raw_attendees]

    names = []
    for attendee in raw_attendees:
        common_name = attendee.params.get("CN") if hasattr(attendee, "params") else None
        if common_name:
            names.append(str(common_name))
        else:
            names.append(str(attendee).replace("mailto:", ""))
    return names[:5]


def _ics_online_url(component) -> str:
    for field in ("LOCATION", "DESCRIPTION"):
        value = component.get(field)
        if not value:
            continue
        match = _URL_PATTERN.search(str(value))
        if match:
            return match.group(0)
    return ""


def fetch() -> dict:
    """Return today's calendar events, or {"error": ...} on failure.

    Uses the published ICS feed (CALENDAR_ICS_URL) when set -- no OAuth required.
    Falls back to the Microsoft Graph work Outlook path otherwise.
    """
    ics_url = os.getenv("CALENDAR_ICS_URL", "").strip()
    if ics_url:
        return _fetch_from_ics(ics_url)
    return _fetch_from_graph()


def _fetch_from_ics(ics_url: str) -> dict:
    """Fetch today's events from a published, read-only ICS calendar feed."""
    cfg = get_config()
    tz_name = cfg.get("timezone", "America/New_York")
    user_tz = pytz.timezone(tz_name)

    try:
        resp = requests.get(ics_url, timeout=15)
        resp.raise_for_status()
        calendar = Calendar.from_ical(resp.text)
    except Exception as exc:
        log.error("ICS calendar fetch failed: %s", exc)
        return {"error": f"Could not fetch or parse the ICS calendar feed: {exc}"}

    today = date.today()
    range_start = user_tz.localize(datetime.combine(today, datetime.min.time()))
    range_end = range_start + timedelta(days=1)

    try:
        occurrences = recurring_ical_events.of(calendar).between(range_start, range_end)
    except Exception as exc:
        log.error("ICS occurrence expansion failed: %s", exc)
        return {"error": f"Could not read events from the ICS calendar feed: {exc}"}

    now = datetime.now(tz=user_tz)
    events = []
    for component in occurrences:
        dtstart = component.get("DTSTART").dt
        dtend_prop = component.get("DTEND")
        dtend = dtend_prop.dt if dtend_prop else dtstart
        is_all_day = not isinstance(dtstart, datetime)

        if is_all_day:
            start_str = end_str = ""
            upcoming = False
        else:
            start_str = _format_local_time(dtstart, user_tz)
            end_str = _format_local_time(dtend, user_tz)
            diff_minutes = (dtstart.astimezone(user_tz) - now).total_seconds() / 60
            upcoming = 0 <= diff_minutes <= 30

        online_url = _ics_online_url(component)
        events.append({
            "subject": str(component.get("SUMMARY", "(No title)")),
            "start": start_str,
            "end": end_str,
            "location": str(component.get("LOCATION", "") or ""),
            "attendees": _ics_attendee_names(component),
            "is_all_day": is_all_day,
            "has_link": bool(online_url),
            "online_url": online_url,
            "upcoming": upcoming,
        })

    events.sort(key=lambda ev: (ev["is_all_day"] is False, ev["start"]))

    return {
        "events": events,
        "count": len(events),
        "date_str": today.strftime("%A, %B %#d %Y"),
    }


def _fetch_from_graph() -> dict:
    """Fetch today's events from the work Outlook calendar via Microsoft Graph."""
    headers = get_headers("work_outlook")
    if not headers:
        return {"error": "Work Microsoft account not authenticated. Run auth/setup_microsoft_work.py"}

    cfg = get_config()
    tz_name = cfg.get("timezone", "America/New_York")
    user_tz = pytz.timezone(tz_name)

    today = date.today()
    start = datetime.combine(today, datetime.min.time()).isoformat() + "Z"
    end = datetime.combine(today + timedelta(days=1), datetime.min.time()).isoformat() + "Z"

    url = (
        f"{GRAPH_BASE}/me/calendarView"
        f"?startDateTime={start}&endDateTime={end}"
        "&$orderby=start/dateTime"
        "&$select=subject,start,end,location,attendees,isAllDay,onlineMeetingUrl"
        "&$top=25"
    )

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        events_raw = resp.json().get("value", [])
    except Exception as exc:
        log.error("Calendar fetch failed: %s", exc)
        return {"error": str(exc)}

    now = datetime.now(tz=user_tz)
    events = []
    for ev in events_raw:
        start_raw = ev.get("start", {})
        end_raw = ev.get("end", {})
        start_str = _parse_dt(start_raw.get("dateTime", ""), start_raw.get("timeZone", "UTC"), user_tz)
        end_str = _parse_dt(end_raw.get("dateTime", ""), end_raw.get("timeZone", "UTC"), user_tz)

        attendees = [
            a["emailAddress"]["name"]
            for a in (ev.get("attendees") or [])
            if a.get("emailAddress", {}).get("name")
        ][:5]

        location = ev.get("location", {}).get("displayName", "") or ""

        # Flag upcoming: starts within 30 minutes
        upcoming = False
        try:
            ev_dt_raw = start_raw.get("dateTime", "")
            ev_tz_raw = start_raw.get("timeZone", "UTC")
            ev_tz = pytz.timezone(ev_tz_raw)
            ev_dt = ev_tz.localize(datetime.fromisoformat(ev_dt_raw)).astimezone(user_tz)
            diff = (ev_dt - now).total_seconds() / 60
            upcoming = 0 <= diff <= 30
        except Exception:
            pass

        events.append({
            "subject": ev.get("subject", "(No title)"),
            "start": start_str,
            "end": end_str,
            "location": location,
            "attendees": attendees,
            "is_all_day": ev.get("isAllDay", False),
            "has_link": bool(ev.get("onlineMeetingUrl")),
            "online_url": ev.get("onlineMeetingUrl") or "",
            "upcoming": upcoming,
        })

    return {
        "events": events,
        "count": len(events),
        "date_str": today.strftime("%A, %B %#d %Y"),
    }
