"""
Shared configuration loader — reads config.yaml once and caches the result.
All modules import `get_config()` to access user preferences.
"""

import functools
import logging
from pathlib import Path

import yaml

log = logging.getLogger(__name__)
_CONFIG_PATH = Path(__file__).parent / "config.yaml"
_DASHBOARD_SECTION_ORDER = ("weather", "calendar", "email", "github", "teams", "news")


def _get_configured_section_list(setting_name: str, default_sections: list[str]) -> list[str]:
    configured_sections = get_config().get("dashboard", {}).get(setting_name)
    if not isinstance(configured_sections, list):
        return list(default_sections)

    configured_lookup = {str(section).strip() for section in configured_sections}
    return [section for section in _DASHBOARD_SECTION_ORDER if section in configured_lookup]


@functools.lru_cache(maxsize=1)
def get_config() -> dict:
    """Load and cache config.yaml from the project root."""
    config_file = Path(__file__).parent / "config.yaml"
    if not config_file.exists():
        log.warning("config.yaml not found at %s — using empty config", config_file)
        return {}
    with config_file.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_enabled_dashboard_sections() -> list[str]:
    """Return dashboard sections enabled in config.yaml, preserving display order."""
    return _get_configured_section_list("enabled_sections", list(_DASHBOARD_SECTION_ORDER))


def get_homepage_dashboard_sections() -> list[str]:
    """Return the dashboard sections rendered on the home page."""
    return _get_configured_section_list("home_sections", get_enabled_dashboard_sections())
