"""
API tests. Run from the backend/ folder:
    pytest -v
"""

import datetime as dt

from app.database.connection import engine


def assert_error(response, status: int, code: str):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]


# ---------- health ----------

def test_health_reports_database(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"]["connected"] is True
    assert body["database"]["dialect"] == engine.dialect.name  # sqlite, or postgresql with TEST_DATABASE_URL
    assert body["database"]["park_count"] == 2
    assert body["database"]["weather_rows"] == 4


def test_cors_allows_frontend_origin(client):
    response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


# ---------- parks ----------

def test_list_parks_sorted(client):
    body = client.get("/api/parks").json()
    assert body["count"] == 2
    assert [p["park_name"] for p in body["parks"]] == sorted(p["park_name"] for p in body["parks"])


def test_list_parks_search(client):
    body = client.get("/api/parks", params={"search": "valley"}).json()
    assert [p["park_code"] for p in body["parks"]] == ["tstv"]


def test_get_park_is_case_insensitive(client):
    response = client.get("/api/parks/TSTP")
    assert response.status_code == 200
    assert response.json()["park_name"] == "Test Peak National Park"


def test_get_unknown_park_returns_404(client):
    assert_error(client.get("/api/parks/nope"), 404, "not_found")


# ---------- history ----------

def test_history_defaults_to_latest_year(client):
    body = client.get("/api/weather/history/tstp").json()
    assert body["count"] == 4
    assert body["end_date"] == "2024-07-11"
    dates = [o["date"] for o in body["observations"]]
    assert dates == sorted(dates)
    assert body["units"]["temperature"] == "celsius"


def test_history_date_filter(client):
    body = client.get("/api/weather/history/tstp",
                      params={"start_date": "2024-07-01", "end_date": "2024-07-31"}).json()
    assert body["count"] == 2


def test_history_empty_for_park_without_data(client):
    body = client.get("/api/weather/history/tstv").json()
    assert body["count"] == 0
    assert body["observations"] == []


def test_history_rejects_reversed_dates(client):
    response = client.get("/api/weather/history/tstp",
                          params={"start_date": "2024-08-01", "end_date": "2024-07-01"})
    assert_error(response, 400, "invalid_request")


# ---------- seasonal (SQL aggregation) ----------

def test_seasonal_monthly_aggregation(client):
    body = client.get("/api/weather/seasonal/tstp").json()
    months = {m["month"]: m for m in body["months"]}
    assert set(months) == {1, 7}
    assert months[1]["avg_temp_max"] == 11.0
    assert months[1]["wet_day_frequency"] == 0.5   # 5.0 mm wet, 0.0 mm dry
    assert months[7]["avg_temp_min"] == 16.0
    assert months[7]["wet_day_frequency"] == 0.5   # 2.0 mm wet, 0.4 mm dry (below threshold)
    assert months[7]["days_observed"] == 2
    assert body["first_date"] == "2024-01-10"


# ---------- predict / compare input validation ----------

def future(days: int = 30) -> str:
    return (dt.date.today() + dt.timedelta(days=days)).isoformat()


def test_predict_unknown_activity_is_422(client):
    response = client.get("/api/weather/predict",
                          params={"park_code": "tstp", "date": future(), "activity": "surfing"})
    assert_error(response, 422, "validation_error")


def test_predict_past_date_is_400(client):
    response = client.get("/api/weather/predict",
                          params={"park_code": "tstp", "date": "2020-01-01"})
    assert_error(response, 400, "invalid_request")


def test_predict_unknown_park_is_404(client):
    response = client.get("/api/weather/predict", params={"park_code": "nope", "date": future()})
    assert_error(response, 404, "not_found")


def test_compare_needs_two_parks(client):
    response = client.post("/api/weather/compare", json={"park_codes": ["tstp"], "date": future()})
    assert_error(response, 422, "validation_error")


def test_compare_rejects_duplicates(client):
    response = client.post("/api/weather/compare",
                           json={"park_codes": ["tstp", "TSTP"], "date": future()})
    assert_error(response, 400, "invalid_request")


def test_unknown_route_uses_error_shape(client):
    assert_error(client.get("/api/does-not-exist"), 404, "not_found")


# ---------- CORS ----------

def test_cors_allows_configured_origin(client):
    response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_blocks_other_origins(client):
    response = client.get("/api/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in response.headers
