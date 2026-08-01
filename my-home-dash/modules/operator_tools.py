"""
Tool registry for the AI Operator (`/api/operator`).

Each entry pairs an Ollama-shaped function schema with a Python handler and an
`action` flag. Read-only tools (`action: False`) run immediately when the model
requests them. Tools with `action: True` must go through a confirmation step
before running (see support/ai_operator/decisions.md, Decision 3) — none exist
yet, so that gate is not wired up until the first one is added.
"""

from __future__ import annotations

from config_loader import get_enabled_dashboard_sections

_ALL_SECTIONS = ("weather", "calendar", "email", "github", "teams", "news")

_DISABLED_SECTION_REASONS = {
    "calendar": "Not enabled in config.yaml. Set CALENDAR_ICS_URL in .env (no Azure app needed) or configure the Microsoft work account and run auth/setup_microsoft_work.py.",
    "email": "Work/home Outlook and Gmail credentials are not fully configured yet.",
    "github": "GITHUB_PAT and the startup 'list index out of range' bug in the GitHub module need to be fixed first.",
    "teams": "Microsoft Teams account credentials in .env are placeholders and tenant admin consent may also be required.",
}


def _get_dashboard_status(arguments: dict, cache: dict) -> dict:
    enabled = set(get_enabled_dashboard_sections())
    disabled = [name for name in _ALL_SECTIONS if name not in enabled]

    section_status = {}
    for name in enabled:
        data = cache.get(name)
        if isinstance(data, dict) and data.get("error"):
            section_status[name] = f"error: {data['error']}"
        elif isinstance(data, dict) and data.get("status") == "pending":
            section_status[name] = "pending"
        else:
            section_status[name] = "ok"

    return {
        "enabled_sections": sorted(enabled),
        "disabled_sections": [
            {"name": name, "reason": _DISABLED_SECTION_REASONS.get(name, "Not yet configured.")}
            for name in disabled
        ],
        "section_status": section_status,
        "last_full_refresh": str(cache.get("last_full_refresh")),
        "last_intraday": str(cache.get("last_intraday")),
    }


_REGISTRY = {
    "get_dashboard_status": {
        "action": False,
        "handler": _get_dashboard_status,
        "schema": {
            "type": "function",
            "function": {
                "name": "get_dashboard_status",
                "description": (
                    "Get the current health and configuration status of My Home Dash: which "
                    "dashboard sections are enabled, which are disabled and why, per-section "
                    "fetch status (ok/pending/error), and when data was last refreshed. Use "
                    "this whenever the user asks whether the dashboard, or a specific section, "
                    "is working."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
    },
}


def tool_schemas() -> list[dict]:
    """Ollama-shaped `tools` payload for every registered tool."""
    return [entry["schema"] for entry in _REGISTRY.values()]


def is_action_tool(name: str) -> bool:
    """True if this tool changes state and must be confirmed before running."""
    entry = _REGISTRY.get(name)
    return True if entry is None else entry["action"]


def dispatch(name: str, arguments: dict, cache: dict) -> dict:
    """Run a registered tool by name and return its JSON-serializable result."""
    entry = _REGISTRY.get(name)
    if entry is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return entry["handler"](arguments or {}, cache)
    except Exception as exc:  # noqa: BLE001 - isolate handler bugs from the tool loop
        return {"error": f"Tool '{name}' failed: {exc}"}
