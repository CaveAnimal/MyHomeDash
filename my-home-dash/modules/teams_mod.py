"""
Microsoft Teams module — fetches unread channel messages and direct messages
via Microsoft Graph API, using the separate Teams account credentials.
"""

import logging

import requests

from auth.microsoft_client import get_headers
from config_loader import get_config

log = logging.getLogger(__name__)
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _fetch_teams_chats(headers: dict, max_items: int) -> list[dict]:
    """Fetch recent unread direct messages / chats."""
    url = f"{GRAPH_BASE}/me/chats?$expand=lastMessagePreview&$top={max_items}"
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        chats = resp.json().get("value", [])
        results = []
        for chat in chats:
            preview = chat.get("lastMessagePreview") or {}
            body = preview.get("body", {}).get("content", "") or ""
            # Strip HTML crudely
            import re
            body = re.sub(r"<[^>]+>", "", body).strip()[:100]
            sender = preview.get("from", {})
            sender_name = (
                sender.get("user", {}).get("displayName")
                or sender.get("application", {}).get("displayName")
                or "Unknown"
            )
            results.append({
                "type": "dm",
                "topic": chat.get("topic") or "Direct Message",
                "sender": sender_name,
                "preview": body or "(no preview)",
                "chat_type": chat.get("chatType", ""),
            })
        return results
    except Exception as exc:
        log.warning("Teams DM fetch failed: %s", exc)
        return []


def _fetch_teams_channels(headers: dict, max_items: int) -> list[dict]:
    """Fetch unread channel mentions/messages."""
    url = f"{GRAPH_BASE}/me/teamwork/associatedTeams?$top=20"
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        teams = resp.json().get("value", [])
    except Exception as exc:
        log.warning("Teams channel list failed: %s", exc)
        return []

    results = []
    for team in teams[:5]:  # Cap to avoid too many API calls
        team_id = team.get("teamId") or team.get("id", "")
        team_name = team.get("displayName", "Unknown Team")
        if not team_id:
            continue
        try:
            ch_url = f"{GRAPH_BASE}/teams/{team_id}/channels?$select=id,displayName&$top=10"
            ch_resp = requests.get(ch_url, headers=headers, timeout=10)
            ch_resp.raise_for_status()
            channels = ch_resp.json().get("value", [])
            for ch in channels[:3]:
                results.append({
                    "type": "channel",
                    "team": team_name,
                    "channel": ch.get("displayName", ""),
                    "channel_id": ch.get("id", ""),
                })
                if len(results) >= max_items:
                    return results
        except Exception as exc:
            log.debug("Channel fetch for team %s failed: %s", team_name, exc)

    return results


def fetch() -> dict:
    """Return Teams DM and channel info, or {"error": ...} on failure."""
    headers = get_headers("teams")
    if not headers:
        return {"error": "Teams account not authenticated. Run auth/setup_microsoft_teams.py"}

    cfg = get_config()
    teams_cfg = cfg.get("teams", {})
    max_items = teams_cfg.get("max_items", 10)

    result: dict = {"dms": [], "channels": [], "dm_count": 0, "channel_count": 0}

    if teams_cfg.get("show_direct_messages", True):
        result["dms"] = _fetch_teams_chats(headers, max_items)
        result["dm_count"] = len(result["dms"])

    if teams_cfg.get("show_channels", True):
        result["channels"] = _fetch_teams_channels(headers, max_items)
        result["channel_count"] = len(result["channels"])

    return result
