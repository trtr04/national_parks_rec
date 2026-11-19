"""
Phase 2 tests: park selection, weather-point choice, the weather transform, upserts
and the analytical SQL. Nothing here calls the NPS or Open-Meteo APIs.
"""

import datetime as dt

from sqlalchemy import func, select

from app.database.connection import SessionLocal
from app.database.models import Park
from app.database.upsert import upsert_rows
from app.services import analytics_service
from scripts.load_parks import build_park_rows, choose_weather_point, is_national_park
from scripts.load_weather_history import transform

# ---------- NPS park loader ----------

NPS_PARKS = [
    {"parkCode": "zion", "fullName": "Zion National Park", "designation": "National Park",
     "states": "UT", "latitude": "37.298", "longitude": "-113.026", "description": "Canyons."},
    {"parkCode": "dena", "fullName": "Denali National Park & Preserve", "designation": "National Park & Preserve",
     "states": "AK", "latitude": "63.30", "longitude": "-151.05", "description": ""},
    {"parkCode": "npsa", "fullName": "National Park of American Samoa", "designation": "",
     "states": "AS", "latitude": "-14.23", "longitude": "-169.85", "description": ""},
    {"parkCode": "kova", "fullName": "Kobuk Valley National Park", "designation": "National Park",
     "states": "AK", "latitude": "67.36", "longitude": "-159.20", "description": ""},
    {"parkCode": "fodo", "fullName": "Fort Donelson National Battlefield", "designation": "National Battlefield",
     "states": "TN", "latitude": "36.48", "longitude": "-87.86", "description": ""},
]
VISITOR_CENTERS = [
    {"parkCode": "zion", "name": "Kolob Canyons Visitor Center", "latitude": "37.4536", "longitude": "-113.2257"},
    {"parkCode": "zion", "name": "Zion Canyon Visitor Center", "latitude": "37.2001", "longitude": "-112.9869"},
    {"parkCode": "dena", "name": "Eielson Visitor Center", "latitude": "63.431", "longitude": "-150.31"},
    {"parkCode": "dena", "name": "Denali Visitor Center", "latitude": "63.7309", "longitude": "-148.917"},
    {"parkCode": "kova", "name": "Northwest Arctic Heritage Center", "latitude": "66.8925", "longitude": "-162.59"},
]


def test_only_national_parks_are_kept():
    assert [p["parkCode"] for p in NPS_PARKS if is_national_park(p)] == ["zion", "dena", "npsa", "kova"]


def test_preferred_visitor_center_wins():
    lat, lon, note = choose_weather_point(NPS_PARKS[1], VISITOR_CENTERS[2:4])
    assert (lat, lon) == (63.7309, -148.917)
    assert "Denali Visitor Center" in note


def test_far_away_visitor_center_falls_back_to_park_centre():
    lat, lon, note = choose_weather_point(NPS_PARKS[3], VISITOR_CENTERS[4:])
    assert (lat, lon) == (67.36, -159.20)
    assert "park centre" in note


def test_build_park_rows():
    rows = {r["park_code"]: r for r in build_park_rows(NPS_PARKS, VISITOR_CENTERS)}
    assert set(rows) == {"zion", "dena", "npsa", "kova"}
    assert rows["zion"]["latitude"] == 37.2001
    assert rows["zion"]["data_source"] == "nps_api"
    assert rows["dena"]["description"] is None


# ---------- Open-Meteo transform ----------

def test_transform_nulls_impossible_values():
    daily = {
        "time": ["2024-01-01", "2024-01-02"],
        "temperature_2m_max": [5.0, 1.0],
        "temperature_2m_min": [-2.0, 3.0],     # day 2: min above max
        "precipitation_sum": [0.0, -1.0],      # day 2: negative
        "rain_sum": [0.0, 0.0],
        "snowfall_sum": [0.0, None],
        "wind_speed_10m_max": [10.0, 12.0],
    }
    rows, nulled = transform("tstp", daily)
    assert rows[0] == {"park_code": "tstp", "date": dt.date(2024, 1, 1), "temp_max": 5.0, "temp_min": -2.0,
                       "precipitation": 0.0, "rainfall": 0.0, "snowfall": 0.0, "wind_speed_max": 10.0}
    assert rows[1]["temp_max"] is None and rows[1]["temp_min"] is None
    assert rows[1]["precipitation"] is None
    assert rows[1]["snowfall"] is None
    assert nulled == 3


def test_upsert_updates_instead_of_duplicating():
    row = {"park_code": "tstx", "park_name": "Upsert Test", "state": "CA",
           "latitude": 1.0, "longitude": 2.0, "data_source": "test"}
    with SessionLocal() as db:
        upsert_rows(db, Park, [row], ["park_code"])
        upsert_rows(db, Park, [{**row, "park_name": "Renamed"}], ["park_code"])
        parks = db.scalars(select(Park).where(Park.park_code == "tstx")).all()
        assert [p.park_name for p in parks] == ["Renamed"]
        db.rollback()  # leave the shared test database untouched


# ---------- analytical SQL ----------

def test_driest_parks_for_month():
    with SessionLocal() as db:
        ranking = analytics_service.driest_parks_for_month(db, 7)
    assert ranking == [{"rank": 1, "park_code": "tstp", "park_name": "Test Peak National Park",
                        "wet_day_frequency": 0.5, "avg_temp_max": 31.0, "days_observed": 2}]


def test_annual_trend():
    with SessionLocal() as db:
        trend = analytics_service.annual_trend(db, "tstp")
    assert len(trend) == 1
    assert trend[0]["year"] == 2024
    assert trend[0]["avg_temp_max"] == 21.0
    assert trend[0]["temp_max_change"] is None          # no previous year
    assert trend[0]["temp_max_rolling_3yr"] == 21.0


def test_date_gaps():
    with SessionLocal() as db:
        gaps = analytics_service.date_gaps(db)
    # Fixtures: Jan 10–11 and Jul 10–11, 2024. Jan 12 .. Jul 9 is 180 missing days.
    assert gaps == [{"park_code": "tstp", "after": dt.date(2024, 1, 11),
                     "before": dt.date(2024, 7, 10), "missing_days": 180}]


# ---------- copy between databases ----------

def test_copy_to_another_database_is_repeatable(tmp_path):
    from app.config import get_settings
    from app.database.connection import build_engine
    from app.database.models import Park, WeatherHistory
    from scripts import copy_to_postgres

    target_url = f"sqlite:///{tmp_path / 'copy.db'}"
    source = get_settings().database_url
    assert copy_to_postgres.main(["--source", source, "--target", target_url]) == 0
    assert copy_to_postgres.main(["--source", source, "--target", target_url]) == 0  # re-run: no duplicates

    count = lambda url, model: build_engine(url).connect().execute(  # noqa: E731
        select(func.count()).select_from(model)).scalar()
    for model in (Park, WeatherHistory):
        assert count(target_url, model) == count(source, model) > 0


def test_copy_refuses_same_database():
    from app.config import get_settings
    from scripts import copy_to_postgres

    url = get_settings().database_url
    assert copy_to_postgres.main(["--source", url, "--target", url]) == 1


def test_postgres_urls_use_psycopg3():
    from app.database.connection import normalize_database_url

    assert normalize_database_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_database_url("postgresql://u:p@h/db?sslmode=require") == "postgresql+psycopg://u:p@h/db?sslmode=require"
    assert normalize_database_url("postgresql+psycopg2://u:p@h/db") == "postgresql+psycopg2://u:p@h/db"
    assert normalize_database_url("sqlite:///x.db") == "sqlite:///x.db"


def test_redact_hides_password():
    from scripts.copy_to_postgres import redact

    assert redact("postgresql://user:secret@host/db") == "postgresql://user:***@host/db"
