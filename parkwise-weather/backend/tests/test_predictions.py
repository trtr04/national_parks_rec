"""
Phase 3 tests: climate estimates, forecasts, comparison, model metrics and the suitability score.

The climate model here is trained on synthetic weather (see conftest.py), and the live
forecast is replaced with a fixed fake, so these tests never touch the network.
"""

import datetime as dt

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.database.connection import SessionLocal
from app.database.models import WeatherPrediction
from app.services import forecast_client
from app.services.suitability import score_day

from tests.test_api import assert_error


def future(days: int) -> str:
    return (dt.date.today() + dt.timedelta(days=days)).isoformat()


FAKE_FORECAST = {
    "temp_max": 18.0, "temp_min": 4.0, "precipitation_probability": 0.2,
    "precipitation": 0.0, "snowfall": 0.0, "wind_speed_max": 15.0,
}


@pytest.fixture()
def fake_forecast(monkeypatch):
    calls = []

    def fake(lat, lon, day):
        calls.append(day)
        return dict(FAKE_FORECAST)

    monkeypatch.setattr(forecast_client, "get_daily_forecast", fake)
    return calls


@pytest.fixture()
def forecast_down(monkeypatch):
    def fail(lat, lon, day):
        raise forecast_client.ForecastUnavailableError("offline")

    monkeypatch.setattr(forecast_client, "get_daily_forecast", fail)


# ---------- climate estimates (beyond 16 days) ----------

def test_climate_estimate_shape_and_ranges(client):
    response = client.get("/api/weather/predict", params={"park_code": "tstp", "date": future(120)})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["prediction_type"] == "climate_estimate"
    assert body["park"]["park_code"] == "tstp"
    t = body["temperature"]
    assert t["max_range_c"][0] < t["max_c"] < t["max_range_c"][1]
    assert t["min_range_c"][0] < t["min_c"] < t["min_range_c"][1]
    assert t["min_c"] <= t["max_c"]
    assert 0 <= body["precipitation"]["probability"] <= 1
    assert body["precipitation"]["kind"] in ("historical_frequency", "climate_model_probability")
    assert 0 <= body["suitability"]["score"] <= 100
    assert body["suitability"]["label"] in ("Excellent", "Good", "Fair", "Poor")
    assert "not a forecast" in body["uncertainty"]
    assert body["summary"]


def test_climate_estimate_follows_the_seasons(client):
    """The synthetic parks peak in late July, so July must be warmer than January."""
    today = dt.date.today()
    july = dt.date(today.year + 1, 7, 25).isoformat()
    january = dt.date(today.year + 1, 1, 20).isoformat()
    warm = client.get("/api/weather/predict", params={"park_code": "tstv", "date": july}).json()
    cold = client.get("/api/weather/predict", params={"park_code": "tstv", "date": january}).json()
    assert warm["temperature"]["max_c"] > cold["temperature"]["max_c"] + 10


def test_predictions_are_logged(client):
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(WeatherPrediction))
    client.get("/api/weather/predict", params={"park_code": "tstv", "date": future(60), "activity": "camping"})
    with SessionLocal() as db:
        rows = db.scalars(select(WeatherPrediction).order_by(WeatherPrediction.prediction_id.desc())).all()
    assert len(rows) == before + 1
    assert rows[0].park_code == "tstv"
    assert rows[0].activity == "camping"
    assert rows[0].prediction_type == "climate_estimate"


def test_model_not_ready_is_503(client, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "model_dir", tmp_path)
    response = client.get("/api/weather/predict", params={"park_code": "tstp", "date": future(60)})
    assert_error(response, 503, "model_not_ready")
    assert_error(client.get("/api/models/performance"), 503, "model_not_ready")


# ---------- forecasts (today to today + 15) ----------

def test_forecast_inside_window(client, fake_forecast):
    body = client.get("/api/weather/predict", params={"park_code": "tstp", "date": future(3)}).json()
    assert body["prediction_type"] == "forecast"
    assert body["source"] == "Open-Meteo Forecast API"
    assert body["temperature"]["max_c"] == 18.0
    assert body["precipitation"] == {"probability": 0.2, "kind": "forecast_probability",
                                     "wet_day_threshold_mm": 1.0, "expected_mm": 0.0}
    assert fake_forecast == [dt.date.today() + dt.timedelta(days=3)]


def test_day_16_is_a_climate_estimate(client, fake_forecast):
    body = client.get("/api/weather/predict", params={"park_code": "tstp", "date": future(16)}).json()
    assert body["prediction_type"] == "climate_estimate"
    assert fake_forecast == []


def test_forecast_outage_falls_back_to_climate(client, forecast_down):
    body = client.get("/api/weather/predict", params={"park_code": "tstp", "date": future(2)}).json()
    assert body["prediction_type"] == "climate_estimate"
    assert any("forecast couldn't be reached" in n for n in body["notes"])


# ---------- compare ----------

def test_compare_ranks_by_suitability(client):
    response = client.post("/api/weather/compare",
                           json={"park_codes": ["tstp", "tstv"], "date": future(90), "activity": "hiking"})
    assert response.status_code == 200, response.text
    body = response.json()
    scores = [r["suitability"]["score"] for r in body["results"]]
    assert scores == sorted(scores, reverse=True)
    assert [r["rank"] for r in body["results"]] == [1, 2]
    assert body["best_park_code"] == body["results"][0]["park"]["park_code"]


def test_compare_unknown_park_is_404(client):
    response = client.post("/api/weather/compare", json={"park_codes": ["tstp", "nope"], "date": future(90)})
    assert_error(response, 404, "not_found")


# ---------- model performance ----------

def test_model_performance(client, trained_model):
    body = client.get("/api/models/performance").json()
    assert set(body["models"]) == {"seasonal_average", "seasonal_regression", "random_forest"}
    assert body["selected_model"] in body["models"]
    assert body["models"]["seasonal_average"]["validation_score"] == 3.0
    for m in body["models"].values():
        assert m["test"]["temp_max_mae"] > 0
        assert 0 <= m["test"]["wet_brier"] <= 1
    # 80% ranges calibrated on validation should cover roughly 80% of test days.
    for coverage in body["interval"]["test_coverage"].values():
        assert 0.7 < coverage < 0.9


def test_model_performance_chart_data(client, trained_model):
    body = client.get("/api/models/performance").json()
    assert set(body["test_temp_max_mae_by_month"]) == set(body["models"])
    hist = body["selected_model_test_error_histogram"]
    assert len(hist["bin_start_c"]) == len(hist["count"]) == 30
    assert 0 < hist["within_3c"] <= 1
    assert 0 < len(body["selected_model_test_sample"]) <= 500


def test_models_beat_nothing_less_than_noise(trained_model):
    """Synthetic noise has sd 3 °C, so a good seasonal model's MAE is near 3 x 0.8 = 2.4 °C."""
    _, metrics = trained_model
    best = metrics["models"][metrics["selected_model"]]["test"]
    assert best["temp_max_mae"] < 2.8


# ---------- suitability score ----------

def test_ideal_hiking_day_scores_100():
    result = score_day("hiking", 20, 8, wet_probability=0, wind_max_kmh=10, snow_probability=0)
    assert result["score"] == 100
    assert result["label"] == "Excellent"


def test_rain_lowers_the_score():
    dry = score_day("sightseeing", 20, 8, 0.0, 10, 0)["score"]
    wet = score_day("sightseeing", 20, 8, 0.8, 10, 0)["score"]
    assert wet == pytest.approx(dry - 0.45 * 80)


def test_extreme_heat_caps_hiking():
    result = score_day("hiking", 42, 28, 0, 5, 0)
    assert result["score"] <= 30
    assert any("heat" in n.lower() for n in result["notes"])


def test_cold_nights_hurt_camping_more_than_hiking():
    camping = score_day("camping", 18, -3, 0, 10, 0)["components"]["temperature"]
    hiking = score_day("hiking", 18, -3, 0, 10, 0)["components"]["temperature"]
    assert camping < hiking


def test_strong_wind_zeroes_wind_component():
    assert score_day("wildlife", 15, 5, 0, 75, 0)["components"]["wind"] == 0


# ---------- best time to visit ----------

def test_best_time_has_twelve_scored_months(client):
    response = client.get("/api/weather/best-time/tstp")
    assert response.status_code == 200, response.text
    body = response.json()
    assert [m["month"] for m in body["months"]] == list(range(1, 13))
    for m in body["months"]:
        assert set(m["scores"]) == {"hiking", "camping", "sightseeing", "wildlife"}
        assert all(0 <= s <= 100 for s in m["scores"].values())
        assert m["temp_min_c"] <= m["temp_max_c"]
    # Synthetic parks peak in summer, so July is warmer than January.
    assert body["months"][6]["temp_max_c"] > body["months"][0]["temp_max_c"]
    assert len(body["best_months"]["hiking"]) == 3


def test_best_time_unknown_park_is_404(client):
    assert_error(client.get("/api/weather/best-time/zzzz"), 404, "not_found")
