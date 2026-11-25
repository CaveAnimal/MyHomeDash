"""
Calendar module — fetches events from the configured Microsoft Graph account or
from a published ICS feed (CALENDAR_ICS_URL, no OAuth required).

`fetch()` supports three views:
  - "day"   : a single day (honours calendar.days_ahead, like the original)
  - "week"  : the Sunday-started week containing the anchor date
  - "month" : the calendar month containing the anchor date, padded to whole weeks
"""

import calendar as _calendar
import logging
import os
import re
from collections import defaultdict
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
_VALID_VIEWS = ("day", "week", "month")
_GRAPH_TIME_ZONES = {
    "America/New_York": "Eastern Standard Time",
    "America/Chicago": "Central Standard Time",
    "America/Denver": "Mountain Standard Time",
    "America/Los_Angeles": "Pacific Standard Time",
}


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


# ── View windows ─────────────────────────────────────────────────────────────

def _week_start(d: date) -> date:
    """Sunday on or before ``d``."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _view_window(view: str, anchor: date, days_ahead: int) -> dict:
    """Return the date range + display metadata for a view anchored on ``anchor``.

    ``grid_start``/``grid_end`` bound what is fetched and drawn (whole weeks for
    the month grid); ``primary_start``/``primary_end`` bound what "belongs" to the
    view for the header count and the in-month shading.
    """
    if view == "week":
        start = _week_start(anchor)
        end = start + timedelta(days=7)
        last = end - timedelta(days=1)
        if start.year != last.year:
            label = f"{start.strftime('%b %#d, %Y')} – {last.strftime('%b %#d, %Y')}"
        elif start.month != last.month:
            label = f"{start.strftime('%b %#d')} – {last.strftime('%b %#d')}"
        else:
            label = f"{start.strftime('%b %#d')} – {last.strftime('%#d')}"
        return {
            "view": view,
            "grid_start": start,
            "grid_end": end,
            "primary_start": start,
            "primary_end": end,
            "label": label,
            "anchor_iso": anchor.isoformat(),
            "prev_iso": (start - timedelta(days=7)).isoformat(),
            "next_iso": end.isoformat(),
        }

    if view == "month":
        month_start = anchor.replace(day=1)
        days_in_month = _calendar.monthrange(month_start.year, month_start.month)[1]
        month_end = month_start + timedelta(days=days_in_month)  # 1st of next month
        grid_start = _week_start(month_start)
        grid_end = _week_start(month_end - timedelta(days=1)) + timedelta(days=7)
        return {
            "view": view,
            "grid_start": grid_start,
            "grid_end": grid_end,
            "primary_start": month_start,
            "primary_end": month_end,
            "label": month_start.strftime("%B %Y"),
            "anchor_iso": anchor.isoformat(),
            "prev_iso": (month_start - timedelta(days=1)).replace(day=1).isoformat(),
            "next_iso": month_end.isoformat(),
        }

    # day
    span = max(1, days_ahead + 1)
    end = anchor + timedelta(days=span)
    return {
        "view": "day",
        "grid_start": anchor,
        "grid_end": end,
        "primary_start": anchor,
        "primary_end": end,
        "label": anchor.strftime("%A, %B %#d %Y"),
        "anchor_iso": anchor.isoformat(),
        "prev_iso": (anchor - timedelta(days=1)).isoformat(),
        "next_iso": (anchor + timedelta(days=1)).isoformat(),
    }


# ── Public entry point ───────────────────────────────────────────────────────

def fetch(view: str = "day", anchor: str | None = None) -> dict:
    """Return calendar events for the requested view, or {"error": ...} on failure.

    Set calendar.source to "ics" to use CALENDAR_ICS_URL. Otherwise the configured
    calendar.account is fetched through Microsoft Graph.
    """
    cfg = get_config()
    calendar_cfg = cfg.get("calendar", {})
    view = view if view in _VALID_VIEWS else "day"

    tz_name = cfg.get("timezone", "America/New_York")
    user_tz = pytz.timezone(tz_name)
    today = datetime.now(user_tz).date()

    try:
        anchor_date = date.fromisoformat(anchor) if anchor else today
    except (TypeError, ValueError):
        anchor_date = today

    days_ahead = max(0, int(calendar_cfg.get("days_ahead", 0)))
    window = _view_window(view, anchor_date, days_ahead)

    if calendar_cfg.get("source") == "ics":
        ics_url = os.getenv("CALENDAR_ICS_URL", "").strip()
        if not ics_url:
            events = {"error": "CALENDAR_ICS_URL is not configured."}
        else:
            events = _events_from_ics(ics_url, window, user_tz)
    else:
        events = _events_from_graph(
            calendar_cfg.get("account", "home_outlook"), window, user_tz
        )

    if isinstance(events, dict):
        return {
            "error": events.get("error", "Calendar fetch failed."),
            "view": view,
            "range_label": window["label"],
            "anchor_iso": window["anchor_iso"],
            "prev_iso": window["prev_iso"],
            "next_iso": window["next_iso"],
            "today_iso": today.isoformat(),
        }

    return _assemble(view, events, window, today)


def create_event(account_id: str, event_data: dict) -> dict:
    """Create a validated event in the configured Outlook calendar."""
    subject = str(event_data.get("subject") or "").strip()
    if not subject:
        return {"error": "Event title is required."}

    try:
        event_date = date.fromisoformat(str(event_data.get("date") or ""))
    except ValueError:
        return {"error": "A valid event date is required."}

    cfg = get_config()
    tz_name = cfg.get("timezone", "America/New_York")
    graph_tz = _GRAPH_TIME_ZONES.get(tz_name, tz_name)
    all_day = event_data.get("all_day") is True

    if all_day:
        start_dt = datetime.combine(event_date, datetime.min.time())
        end_dt = start_dt + timedelta(days=1)
    else:
        try:
            start_time = datetime.strptime(str(event_data.get("start_time") or ""), "%H:%M").time()
            end_time = datetime.strptime(str(event_data.get("end_time") or ""), "%H:%M").time()
        except ValueError:
            return {"error": "Valid start and end times are required."}
        start_dt = datetime.combine(event_date, start_time)
        end_dt = datetime.combine(event_date, end_time)
        if end_dt <= start_dt:
            return {"error": "End time must be after start time."}

    headers = get_headers(account_id)
    if not headers:
        return {"error": "Home Outlook is not authenticated."}

    payload = {
        "subject": subject[:255],
        "isAllDay": all_day,
        "showAs": "busy",
        "start": {"dateTime": start_dt.isoformat(), "timeZone": graph_tz},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": graph_tz},
    }
    location = str(event_data.get("location") or "").strip()
    notes = str(event_data.get("notes") or "").strip()
    if location:
        payload["location"] = {"displayName": location[:255]}
    if notes:
        payload["body"] = {"contentType": "text", "content": notes[:2000]}

    try:
        response = requests.post(
            f"{GRAPH_BASE}/me/events",
            headers=headers,
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        created = response.json()
        return {
            "id": created.get("id"),
            "subject": created.get("subject", subject),
            "web_link": created.get("webLink", ""),
        }
    except Exception as exc:
        log.error("Calendar event creation failed: %s", exc)
        return {"error": str(exc)}


# ── Source fetchers — each returns a flat list of event dicts (day_iso tagged) ─

def _graph_local_date(start_raw: dict, is_all_day: bool, user_tz) -> str:
    """Local calendar date (ISO) an event falls on."""
    dt_str = start_raw.get("dateTime", "") or ""
    if is_all_day:
        return dt_str[:10]
    try:
        tz = pytz.timezone(start_raw.get("timeZone") or "UTC")
        local_dt = tz.localize(datetime.fromisoformat(dt_str)).astimezone(user_tz)
        return local_dt.date().isoformat()
    except Exception:
        return dt_str[:10]


def _graph_is_upcoming(start_raw: dict, now: datetime, user_tz) -> bool:
    try:
        ev_tz = pytz.timezone(start_raw.get("timeZone", "UTC"))
        ev_dt = ev_tz.localize(
            datetime.fromisoformat(start_raw.get("dateTime", ""))
        ).astimezone(user_tz)
        diff = (ev_dt - now).total_seconds() / 60
        return 0 <= diff <= 30
    except Exception:
        return False


def _events_from_graph(account_id: str, window: dict, user_tz) -> list | dict:
    """Fetch events for the window from a Microsoft Outlook calendar via Graph."""
    headers = get_headers(account_id)
    if not headers:
        setup_name = account_id.replace("_outlook", "")
        return {"error": f"Microsoft account not authenticated. Run auth/setup_microsoft_{setup_name}.py"}

    range_start = user_tz.localize(datetime.combine(window["grid_start"], datetime.min.time()))
    range_end = user_tz.localize(datetime.combine(window["grid_end"], datetime.min.time()))

    url = (
        f"{GRAPH_BASE}/me/calendarView"
        f"?startDateTime={range_start.isoformat()}&endDateTime={range_end.isoformat()}"
        "&$orderby=start/dateTime"
        "&$select=subject,start,end,location,attendees,isAllDay,onlineMeetingUrl"
        "&$top=500"
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
        is_all_day = ev.get("isAllDay", False)

        attendees = [
            a["emailAddress"]["name"]
            for a in (ev.get("attendees") or [])
            if a.get("emailAddress", {}).get("name")
        ][:5]

        events.append({
            "subject": ev.get("subject", "(No title)"),
            "start": _parse_dt(start_raw.get("dateTime", ""), start_raw.get("timeZone", "UTC"), user_tz),
            "end": _parse_dt(end_raw.get("dateTime", ""), end_raw.get("timeZone", "UTC"), user_tz),
            "location": ev.get("location", {}).get("displayName", "") or "",
            "attendees": attendees,
            "is_all_day": is_all_day,
            "has_link": bool(ev.get("onlineMeetingUrl")),
            "online_url": ev.get("onlineMeetingUrl") or "",
            "day_iso": _graph_local_date(start_raw, is_all_day, user_tz),
            "upcoming": _graph_is_upcoming(start_raw, now, user_tz),
        })

    return events


def _events_from_ics(ics_url: str, window: dict, user_tz) -> list | dict:
    """Fetch events for the window from a published, read-only ICS calendar feed."""
    try:
        resp = requests.get(ics_url, timeout=15)
        resp.raise_for_status()
        calendar = Calendar.from_ical(resp.text)
    except Exception as exc:
        log.error("ICS calendar fetch failed: %s", exc)
        return {"error": f"Could not fetch or parse the ICS calendar feed: {exc}"}

    range_start = user_tz.localize(datetime.combine(window["grid_start"], datetime.min.time()))
    range_end = user_tz.localize(datetime.combine(window["grid_end"], datetime.min.time()))

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
            day_iso = dtstart.isoformat()
            upcoming = False
        else:
            local_start = dtstart.astimezone(user_tz)
            start_str = _format_local_time(dtstart, user_tz)
            end_str = _format_local_time(dtend, user_tz)
            day_iso = local_start.date().isoformat()
            diff_minutes = (local_start - now).total_seconds() / 60
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
            "day_iso": day_iso,
            "upcoming": upcoming,
        })

    return events


# ── View assembly ────────────────────────────────────────────────────────────

def _sort_day(events: list) -> list:
    """All-day events first, then timed events by start time string."""
    return sorted(events, key=lambda e: (e["is_all_day"] is False, e["start"]))


def _day_cells(events: list, start: date, end: date, today: date, month: int | None) -> list:
    by_day: dict[str, list] = defaultdict(list)
    for e in events:
        by_day[e["day_iso"]].append(e)

    cells = []
    d = start
    while d < end:
        iso = d.isoformat()
        day_events = _sort_day(by_day.get(iso, []))
        cells.append({
            "iso": iso,
            "day_num": d.day,
            "weekday_label": d.strftime("%a"),
            "date_label": d.strftime("%A, %B %#d"),
            "in_month": month is None or d.month == month,
            "is_today": d == today,
            "events": day_events,
            "count": len(day_events),
        })
        d += timedelta(days=1)
    return cells


def _assemble(view: str, events: list, window: dict, today: date) -> dict:
    ps_iso = window["primary_start"].isoformat()
    pe_iso = window["primary_end"].isoformat()
    primary = _sort_day([e for e in events if ps_iso <= e["day_iso"] < pe_iso])
    primary.sort(key=lambda e: (e["day_iso"], e["is_all_day"] is False, e["start"]))

    data = {
        "view": view,
        "events": primary,
        "count": len(primary),
        "range_label": window["label"],
        "anchor_iso": window["anchor_iso"],
        "prev_iso": window["prev_iso"],
        "next_iso": window["next_iso"],
        "today_iso": today.isoformat(),
        # Kept for backward compatibility with the day-view template/consumers.
        "date_str": window["primary_start"].strftime("%A, %B %#d %Y"),
    }

    if view == "day":
        return data

    cells = _day_cells(
        events,
        window["grid_start"],
        window["grid_end"],
        today,
        month=window["primary_start"].month if view == "month" else None,
    )
    if view == "week":
        data["days"] = cells
    else:
        data["weeks"] = [cells[i:i + 7] for i in range(0, len(cells), 7)]
        data["weekday_headers"] = [
            (window["grid_start"] + timedelta(days=i)).strftime("%a") for i in range(7)
        ]
    return data
