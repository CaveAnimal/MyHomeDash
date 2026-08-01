"""
Weather module — fetches forecast from up to 3 sources and averages them.

Sources:
  - Open-Meteo (no API key)
  - OpenWeatherMap (free tier key: OPENWEATHERMAP_API_KEY)
  - WeatherAPI.com (free tier key: WEATHERAPI_KEY)

Returns a dict with averaged high/low, conditions, and per-source breakdown.
Any source that fails is skipped; the rest still run.
"""

import logging
import os
from datetime import datetime
from statistics import mean

import requests
from dotenv import load_dotenv

from config_loader import get_config

load_dotenv()
log = logging.getLogger(__name__)


def _get_open_meteo(lat: float, lon: float, units: str) -> dict | None:
    """Open-Meteo: free, no key required."""
    temp_unit = "fahrenheit" if units == "imperial" else "celsius"
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode"
        f"&temperature_unit={temp_unit}&timezone=auto&forecast_days=1"
    )
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()["daily"]
        wcode = data.get("weathercode", [None])[0]
        return {
            "source": "Open-Meteo",
            "high": data["temperature_2m_max"][0],
            "low": data["temperature_2m_min"][0],
            "precip_pct": data.get("precipitation_probability_max", [None])[0],
            "condition": _wmo_condition(wcode),
        }
    except Exception as exc:
        log.warning("Open-Meteo failed: %s", exc)
        return None


_RAIN_CODES = {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96}


def _hourly_icon(weathercode: int | None, is_day: int) -> str:
    """Collapse a WMO weather code + day/night flag down to sun/cloud/moon/rain."""
    if weathercode in (0, 1):
        return "sun" if is_day else "moon"
    if weathercode in _RAIN_CODES:
        return "rain"
    return "cloud"


def _get_open_meteo_hourly(lat: float, lon: float, units: str, hours: int = 24) -> list[dict]:
    """Open-Meteo hourly temperatures + sky icon for the next `hours` hours (predictive graph)."""
    temp_unit = "fahrenheit" if units == "imperial" else "celsius"
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,weathercode,is_day"
        f"&temperature_unit={temp_unit}&timezone=auto&forecast_days=3"
    )
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        hourly = r.json()["hourly"]
        current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)

        points = []
        for time_str, temp, wcode, is_day in zip(
            hourly["time"], hourly["temperature_2m"], hourly["weathercode"], hourly["is_day"]
        ):
            dt = datetime.fromisoformat(time_str)
            if dt < current_hour:
                continue
            # %-I is a glibc-only strftime extension and raises on Windows; strip the
            # leading zero manually instead so this works cross-platform.
            label = dt.strftime("%I %p").lstrip("0")
            # Same portability note as above -- build the day-of-month from the int
            # rather than a %-d strftime flag, which Windows doesn't support.
            full_date = f"{dt.strftime('%a, %b')} {dt.day}"
            points.append({
                "time": label,
                "temp": round(temp),
                "icon": _hourly_icon(wcode, is_day),
                "full_date": full_date,
            })
            if len(points) >= hours:
                break
        return points
    except Exception as exc:
        log.warning("Open-Meteo hourly failed: %s", exc)
        return []


def _wmo_condition(code: int | None) -> str:
    """Map WMO weather code to a human-readable string."""
    if code is None:
        return "Unknown"
    mapping = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Icy fog",
        51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
        61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
        71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
        80: "Slight showers", 81: "Moderate showers", 82: "Heavy showers",
        95: "Thunderstorm", 96: "Thunderstorm with hail",
    }
    return mapping.get(code, f"Code {code}")


def _get_openweathermap(lat: float, lon: float, units: str) -> dict | None:
    api_key = os.getenv("OPENWEATHERMAP_API_KEY", "")
    if not api_key:
        log.debug("OPENWEATHERMAP_API_KEY not set — skipping")
        return None
    owm_units = "imperial" if units == "imperial" else "metric"
    url = (
        f"https://api.openweathermap.org/data/2.5/forecast"
        f"?lat={lat}&lon={lon}&appid={api_key}&units={owm_units}&cnt=8"
    )
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        items = r.json()["list"]
        temps = [i["main"]["temp"] for i in items]
        condition = items[0]["weather"][0]["description"].title() if items else "Unknown"
        pop = max((i.get("pop", 0) for i in items), default=0)
        return {
            "source": "OpenWeatherMap",
            "high": max(temps),
            "low": min(temps),
            "precip_pct": round(pop * 100),
            "condition": condition,
        }
    except Exception as exc:
        log.warning("OpenWeatherMap failed: %s", exc)
        return None


def _get_weatherapi(lat: float, lon: float, units: str) -> dict | None:
    api_key = os.getenv("WEATHERAPI_KEY", "")
    if not api_key:
        log.debug("WEATHERAPI_KEY not set — skipping")
        return None
    url = f"https://api.weatherapi.com/v1/forecast.json?key={api_key}&q={lat},{lon}&days=1"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        day = r.json()["forecast"]["forecastday"][0]["day"]
        field = "maxtemp_f" if units == "imperial" else "maxtemp_c"
        low_field = "mintemp_f" if units == "imperial" else "mintemp_c"
        return {
            "source": "WeatherAPI",
            "high": day[field],
            "low": day[low_field],
            "precip_pct": round(day.get("daily_chance_of_rain", 0)),
            "condition": day["condition"]["text"],
        }
    except Exception as exc:
        log.warning("WeatherAPI failed: %s", exc)
        return None


def fetch() -> dict:
    """
    Fetch weather from all configured sources and return averaged data.
    Returns: { high, low, precip_pct, condition, units, sources: [...] }
    """
    cfg = get_config()
    loc = cfg.get("location", {})
    lat = loc.get("lat", 40.7128)
    lon = loc.get("lon", -74.0060)
    units = cfg.get("weather", {}).get("units", "imperial")
    enabled = cfg.get("weather", {}).get("sources", ["open_meteo", "openweathermap", "weatherapi"])

    fetchers = {
        "open_meteo": lambda: _get_open_meteo(lat, lon, units),
        "openweathermap": lambda: _get_openweathermap(lat, lon, units),
        "weatherapi": lambda: _get_weatherapi(lat, lon, units),
    }

    results = []
    for key in enabled:
        fn = fetchers.get(key)
        if fn:
            result = fn()
            if result:
                results.append(result)

    if not results:
        return {"error": "All weather sources failed"}

    avg_high = round(mean(r["high"] for r in results), 1)
    avg_low = round(mean(r["low"] for r in results), 1)
    precip_values = [r["precip_pct"] for r in results if r.get("precip_pct") is not None]
    avg_precip = round(mean(precip_values)) if precip_values else None

    # Use condition from first successful source
    condition = results[0]["condition"]

    unit_sym = "°F" if units == "imperial" else "°C"
    return {
        "high": avg_high,
        "low": avg_low,
        "precip_pct": avg_precip,
        "condition": condition,
        "units": unit_sym,
        "sources": results,
        "source_count": len(results),
        "hourly": _get_open_meteo_hourly(lat, lon, units),
    }
