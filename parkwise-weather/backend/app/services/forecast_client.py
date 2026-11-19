"""
Live short-range forecast from the Open-Meteo Forecast API (no key needed).

Used for travel dates inside the forecast window (today + 15 days). Responses are
cached in memory for an hour per park, so many requests for the same park make
one upstream call.
"""

import datetime as dt
import time

import requests

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 16
CACHE_SECONDS = 3600
TIMEOUT_SECONDS = 10

DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
    "precipitation_sum",
    "snowfall_sum",
    "wind_speed_10m_max",
]

_cache: dict[tuple[float, float], tuple[float, dict]] = {}


class ForecastUnavailableError(Exception):
    """Open-Meteo couldn't be reached or didn't cover the date."""


def _fetch(latitude: float, longitude: float) -> dict:
    key = (round(latitude, 4), round(longitude, 4))
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]
    try:
        response = requests.get(
            FORECAST_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "daily": ",".join(DAILY_VARIABLES),
                "timezone": "auto",
                "forecast_days": FORECAST_DAYS,
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ForecastUnavailableError(str(exc)) from exc
    _cache[key] = (time.monotonic(), payload)
    return payload


def get_daily_forecast(latitude: float, longitude: float, day: dt.date) -> dict:
    """
    Forecast for one day: {"temp_max", "temp_min", "precipitation_probability" (0–1 or None),
    "precipitation", "snowfall", "wind_speed_max"} in °C, mm, cm, km/h.
    """
    daily = _fetch(latitude, longitude).get("daily", {})
    try:
        i = daily["time"].index(day.isoformat())
    except (KeyError, ValueError) as exc:
        raise ForecastUnavailableError(f"No forecast for {day}") from exc

    def value(name):
        return daily.get(name, [None] * (i + 1))[i]

    if value("temperature_2m_max") is None or value("temperature_2m_min") is None:
        raise ForecastUnavailableError(f"Forecast for {day} has no temperatures")
    probability = value("precipitation_probability_max")
    return {
        "temp_max": value("temperature_2m_max"),
        "temp_min": value("temperature_2m_min"),
        "precipitation_probability": None if probability is None else probability / 100.0,
        "precipitation": value("precipitation_sum"),
        "snowfall": value("snowfall_sum"),
        "wind_speed_max": value("wind_speed_10m_max"),
    }
