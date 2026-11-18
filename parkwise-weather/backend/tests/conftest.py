"""
Test setup: every test run uses its own throwaway SQLite file, never your real database.

DATABASE_URL must be set *before* the app is imported, because the engine is
created at import time — that's why this happens at the top of the file.

The few weather rows inserted below are hand-written test fixtures used only to
check the SQL aggregation math. They never touch the real database.

Set TEST_DATABASE_URL to run the same tests against PostgreSQL instead (CI does this).
That database is emptied at the start of the run, so never point it at real data.

The climate model used by the prediction tests is trained on synthetic weather
(tests/synthetic.py) and saved to the temporary MODEL_DIR, never to trained_models/.
"""

import datetime as dt
import os
import tempfile
from pathlib import Path

_TMP_DIR = tempfile.mkdtemp(prefix="parkwise-test-")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{Path(_TMP_DIR) / 'test.db'}"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
os.environ["ENVIRONMENT"] = "test"
os.environ["MODEL_DIR"] = str(Path(_TMP_DIR) / "models")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import joblib  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database.connection import Base, SessionLocal, engine, init_db  # noqa: E402
from app.database.models import Park, WeatherHistory  # noqa: E402
from app.main import app  # noqa: E402
from scripts.train_models import BUNDLE_FILE, METRICS_FILE, Split, train_and_evaluate  # noqa: E402
from tests.synthetic import synthetic_history  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded_database():
    from app.database import models  # noqa: F401  (registers the tables on Base)

    Base.metadata.drop_all(bind=engine)  # a clean slate (matters for a reused Postgres test database)
    init_db()
    with SessionLocal() as db:
        db.merge(Park(park_code="tstp", park_name="Test Peak National Park", state="CA",
                      latitude=37.0, longitude=-119.0, data_source="test"))
        db.merge(Park(park_code="tstv", park_name="Test Valley National Park", state="UT",
                      latitude=37.2, longitude=-113.0, data_source="test"))
        fixtures = [
            # date,              tmax, tmin, precip
            (dt.date(2024, 1, 10), 10.0, 0.0, 0.0),
            (dt.date(2024, 1, 11), 12.0, 2.0, 5.0),
            (dt.date(2024, 7, 10), 30.0, 15.0, 0.4),   # 0.4 mm is below the 1 mm wet-day threshold
            (dt.date(2024, 7, 11), 32.0, 17.0, 2.0),
        ]
        for day, tmax, tmin, precip in fixtures:
            db.merge(WeatherHistory(park_code="tstp", date=day, temp_max=tmax, temp_min=tmin,
                                    precipitation=precip, rainfall=precip, snowfall=0.0,
                                    wind_speed_max=10.0))
        db.commit()
    yield


@pytest.fixture(scope="session", autouse=True)
def trained_model():
    """Train on synthetic 2015–2025 weather for both test parks and save it where the API looks."""
    import json

    bundle, metrics = train_and_evaluate(synthetic_history(), Split())
    model_dir = get_settings().model_dir
    model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, model_dir / BUNDLE_FILE)
    (model_dir / METRICS_FILE).write_text(json.dumps(metrics))
    return bundle, metrics


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client
