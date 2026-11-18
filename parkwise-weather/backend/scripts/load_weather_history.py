"""
Phase 2 weather ETL: daily history 2015–2025 from the Open-Meteo archive into `weather_history`.

Usage, from the backend/ folder (after scripts.load_parks):
    python -m scripts.load_weather_history                  # every park, 2015–2025
    python -m scripts.load_weather_history --parks yose,zion
    python -m scripts.load_weather_history --start-year 2020 --end-year 2025
    python -m scripts.load_weather_history --force          # re-download complete years too

How it works
    * Extract: one archive request per park per calendar year, at the park's weather
      point (parks.latitude / longitude). The archive is ERA5-based reanalysis.
      Years are loaded newest first, all parks per year.
    * Transform: rows are checked against the table's rules (no negative precipitation,
      snowfall or wind, temp_min <= temp_max). Bad values become NULL and are counted.
    * Load: rows are upserted on (park_code, date), so re-running never duplicates.

Resumable
    A (park, year) that already has a row for every day is skipped, so the script can
    be stopped and restarted at any point.

Rate limits
    Open-Meteo's free tier counts a long request as many calls (about one per two
    weeks of data), so 63 parks x 11 years is more than one day's allowance. On a
    per-minute or per-hour limit the script waits and continues by itself. On the
    daily limit it stops; run it again tomorrow and it picks up where it stopped.

Progress is logged to the console and to data/etl_weather.log.
"""

import argparse
import calendar
import datetime as dt
import logging
import sys
import time

import requests
from sqlalchemy import func, select

from app.config import PROJECT_DIR
from app.database.connection import SessionLocal, init_db
from app.database.models import Park, WeatherHistory
from app.database.upsert import upsert_rows
from scripts.http_client import RateLimitedError, get_json

logger = logging.getLogger("parkwise.etl.weather")

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DEFAULT_START_YEAR = 2015
DEFAULT_END_YEAR = 2025

# Open-Meteo variable -> weather_history column. Units are Open-Meteo's defaults.
DAILY_VARIABLES = {
    "temperature_2m_max": "temp_max",          # °C
    "temperature_2m_min": "temp_min",          # °C
    "precipitation_sum": "precipitation",      # mm
    "rain_sum": "rainfall",                    # mm
    "snowfall_sum": "snowfall",                # cm
    "wind_speed_10m_max": "wind_speed_max",    # km/h
}
NON_NEGATIVE = ("precipitation", "rainfall", "snowfall", "wind_speed_max")

PAUSE_BETWEEN_REQUESTS_S = 1.0


class DailyLimitReached(Exception):
    pass


def days_in_year(year: int) -> int:
    return 366 if calendar.isleap(year) else 365


def transform(park_code: str, daily: dict) -> tuple[list[dict], int]:
    """Turn Open-Meteo's column arrays into table rows. Returns (rows, values_nulled)."""
    rows: list[dict] = []
    nulled = 0
    for i, day in enumerate(daily["time"]):
        row = {"park_code": park_code, "date": dt.date.fromisoformat(day)}
        for api_name, column in DAILY_VARIABLES.items():
            value = daily[api_name][i]
            row[column] = None if value is None else float(value)

        for column in NON_NEGATIVE:
            if row[column] is not None and row[column] < 0:
                row[column] = None
                nulled += 1
        if row["temp_min"] is not None and row["temp_max"] is not None and row["temp_min"] > row["temp_max"]:
            row["temp_min"] = row["temp_max"] = None
            nulled += 2
        rows.append(row)
    return rows, nulled


def stored_days(db, park_code: str, year: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(WeatherHistory)
        .where(WeatherHistory.park_code == park_code)
        .where(WeatherHistory.date.between(dt.date(year, 1, 1), dt.date(year, 12, 31)))
    )


def fetch_year(session: requests.Session, park: Park, year: int) -> dict:
    """Download one park-year, waiting out per-minute and per-hour rate limits."""
    params = {
        "latitude": park.latitude,
        "longitude": park.longitude,
        "start_date": f"{year}-01-01",
        "end_date": f"{year}-12-31",
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": "auto",  # days run midnight to midnight in the park's own time zone
    }
    while True:
        try:
            return get_json(session, ARCHIVE_URL, params=params)
        except RateLimitedError as exc:
            reason = exc.reason.lower()
            if "daily" in reason:
                raise DailyLimitReached(exc.reason) from exc
            if "hourly" in reason:
                now = dt.datetime.now()
                wait = 3600 - now.minute * 60 - now.second + 60
            else:
                wait = 65
            logger.warning("Rate limited (%s). Waiting %d s, then continuing.", exc.reason, wait)
            time.sleep(wait)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load daily weather history from Open-Meteo.")
    parser.add_argument("--parks", help="Comma-separated park codes (default: every park)")
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument("--force", action="store_true", help="Re-download years that are already complete")
    args = parser.parse_args(argv)

    log_file = PROJECT_DIR / "data" / "etl_weather.log"
    log_file.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_file)],
    )

    last_full_year = dt.date.today().year - 1
    if args.end_year > last_full_year:
        parser.error(f"--end-year must be {last_full_year} or earlier (the archive needs complete years).")
    years = range(args.start_year, args.end_year + 1)

    init_db()
    with SessionLocal() as db:
        stmt = select(Park).order_by(Park.park_code)
        if args.parks:
            codes = [c.strip().lower() for c in args.parks.split(",") if c.strip()]
            stmt = stmt.where(Park.park_code.in_(codes))
        parks = list(db.scalars(stmt))
    if not parks:
        logger.error("No parks found. Run `python -m scripts.load_parks` first.")
        return 1

    # Newest year first, all parks per year: if the daily limit stops the run, every
    # park already has its most recent years instead of some parks having nothing.
    jobs = [(park, year) for year in reversed(years) for park in parks]
    loaded = skipped = failed = 0
    logger.info("Weather ETL: %d parks x %d years = %d park-years", len(parks), len(years), len(jobs))

    with requests.Session() as session:
        for n, (park, year) in enumerate(jobs, start=1):
            with SessionLocal() as db:
                if not args.force and stored_days(db, park.park_code, year) >= days_in_year(year):
                    skipped += 1
                    continue
                try:
                    payload = fetch_year(session, park, year)
                except DailyLimitReached as exc:
                    logger.warning("Daily Open-Meteo limit reached (%s).", exc)
                    logger.warning("Stopped at %s %d. Run this script again tomorrow to continue.", park.park_code, year)
                    break
                except Exception:  # one bad park-year shouldn't stop the whole run
                    logger.exception("Failed: %s %d", park.park_code, year)
                    failed += 1
                    continue

                rows, nulled = transform(park.park_code, payload["daily"])
                upsert_rows(db, WeatherHistory, rows, ["park_code", "date"])
                db.commit()
                loaded += 1
                logger.info(
                    "[%d/%d] %s %d: %d days (grid elevation %.0f m)%s",
                    n, len(jobs), park.park_code, year, len(rows), payload.get("elevation", float("nan")),
                    f", {nulled} invalid values set to NULL" if nulled else "",
                )
            time.sleep(PAUSE_BETWEEN_REQUESTS_S)

    remaining = len(jobs) - loaded - skipped - failed
    logger.info(
        "Done. Loaded %d park-years, skipped %d already complete, %d failed, %d not reached.",
        loaded, skipped, failed, remaining,
    )
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
