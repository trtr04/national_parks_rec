"""Park recommender: feature loading, filters, scoring and the API."""

import pytest

from app.database.connection import SessionLocal
from app.database.models import ParkFeatures
from app.services import park_recommender as rec
from scripts.load_park_features import build_feature_rows, open_months

# Test Peak: mountains, lakes, elk, campground with showers, $30 vehicle fee.
# Test Valley: canyons only, no campground, no vehicle fee.
PEAK = dict(park_code="tstp", topics=["Mountains", "Lakes", "Elk"],
            activities=["Hiking", "Wildlife Watching", "RV Camping"],
            campground_count=2, campgrounds_with_showers=1, visitor_center_count=1,
            vehicle_fee_usd=30.0, nps_url="https://www.nps.gov/tstp/",
            image_url="https://example.org/a.jpg", image_alt="A peak", image_credit="NPS Photo")
VALLEY = dict(park_code="tstv", topics=["Canyons and Canyonlands"], activities=["Hiking"],
              campground_count=0, campgrounds_with_showers=0, visitor_center_count=0,
              vehicle_fee_usd=None, nps_url=None,
              image_url="https://example.org/b.jpg", image_alt=None, image_credit="J. Smith")


@pytest.fixture(scope="module", autouse=True)
def features():
    with SessionLocal() as db:
        db.merge(ParkFeatures(**PEAK))
        db.merge(ParkFeatures(**VALLEY))
        db.commit()
    yield
    with SessionLocal() as db:
        db.query(ParkFeatures).delete()
        db.commit()


def run(**kwargs):
    with SessionLocal() as db:
        return rec.recommend_parks(db, rec.ParkPreferences(**kwargs))


def codes(result):
    return [r["park_code"] for r in result["results"]]


# ---------- loading ----------

def test_build_feature_rows_counts_and_fees():
    parks = [
        {"parkCode": "tstp", "topics": [{"name": "Lakes"}, {"name": "Lakes"}], "activities": [{"name": "Hiking"}],
         "entranceFees": [{"title": "Entrance - Private Vehicle", "cost": "30.00"}],
         "images": [{"url": "u", "altText": "a", "credit": "NPS Photo"}], "url": "https://nps.gov/tstp"},
        {"parkCode": "zzzz", "topics": [], "activities": [], "entranceFees": [], "images": []},
    ]
    camps = [
        {"parkCode": "tstp", "amenities": {"showers": ["Hot - Seasonal"]}},
        {"parkCode": "tstp", "amenities": {"showers": ["None"]}},
    ]
    rows = build_feature_rows(parks, camps, [{"parkCode": "tstp"}], {"tstp"})
    assert len(rows) == 1  # zzzz isn't in the parks table
    row = rows[0]
    assert row["topics"] == ["Lakes"]
    assert (row["campground_count"], row["campgrounds_with_showers"], row["visitor_center_count"]) == (2, 1, 1)
    assert row["vehicle_fee_usd"] == 30.0


def test_open_months_from_seasonal_closures():
    all_day = {d: "All Day" for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")}
    closed = {d: "Closed" for d in all_day}
    summer_only = {"operatingHours": [{"standardHours": all_day, "exceptions": [
        {"name": "Closed Seasonally", "startDate": "2026-10-12", "endDate": "2027-05-23", "exceptionHours": closed},
    ]}]}
    assert open_months(summer_only) == [False] * 5 + [True] * 4 + [False] * 3  # open June–September
    assert open_months({"operatingHours": [{"standardHours": all_day, "exceptions": []}]}) == [True] * 12
    assert open_months({"operatingHours": [{"standardHours": closed}]}) == [False] * 12
    assert open_months({}) == [True] * 12  # nothing listed: assume open


# ---------- filters ----------

def test_camping_requires_a_campground():
    result = run(month=7, activity="camping")
    assert codes(result) == ["tstp"]
    assert result["excluded"]["tstv"]["park_name"] == "Test Valley National Park"
    assert "campground" in result["excluded"]["tstv"]["reason"]


def test_must_have_amenities_filter():
    assert codes(run(month=7, amenities=("no_vehicle_fee",))) == ["tstv"]
    assert codes(run(month=7, amenities=("showers", "visitor_center"))) == ["tstp"]


def test_max_distance_filter_and_reason():
    # Test Peak (37.0, -119.0) is about 200 miles from San Francisco; Test Valley is ~530.
    result = run(month=7, origin="San Francisco, CA", max_miles=300)
    assert codes(result) == ["tstp"]
    assert "miles away" in result["excluded"]["tstv"]["reason"]
    assert result["nearest_beyond_limit"]["park_code"] == "tstv"


def test_nothing_in_range_names_the_nearest_park():
    result = run(month=7, origin="San Francisco, CA", max_miles=50)
    assert result["results"] == []
    assert result["nearest_beyond_limit"]["park_code"] == "tstp"
    assert 150 < result["nearest_beyond_limit"]["distance_miles"] < 250


def test_campground_seasons_limit_camping():
    closed_in_winter = [0, 0, 0, 0, 1, 2, 2, 2, 1, 0, 0, 0]
    with SessionLocal() as db:
        db.get(ParkFeatures, "tstp").campground_open_months = closed_in_winter
        db.commit()
    try:
        assert codes(run(month=1, activity="camping", include_poor_weather=True)) == []
        summer = run(month=7, activity="camping", include_poor_weather=True)
        assert codes(summer) == ["tstp"]
        may = run(month=5, activity="camping", include_poor_weather=True)["results"][0]
        assert "1 of 2 campgrounds" in " ".join(may["warnings"])
    finally:
        with SessionLocal() as db:
            db.get(ParkFeatures, "tstp").campground_open_months = None
            db.commit()


def test_poor_weather_is_hidden_unless_asked():
    # The cool, wet test park is poor for camping in January (cold nights).
    hidden = run(month=1, activity="camping")
    shown = run(month=1, activity="camping", include_poor_weather=True)
    assert hidden["poor_weather_hidden"] >= 1
    assert "poor" in hidden["excluded"]["tstp"]["reason"]
    assert codes(shown) == ["tstp"]
    assert shown["results"][0]["warnings"]


def test_road_access_filter_and_warning(monkeypatch):
    monkeypatch.setitem(rec.NO_ROAD_ACCESS, "tstv", "Boat only.")
    assert codes(run(month=7, amenities=("road_access",))) == ["tstp"]
    valley = {r["park_code"]: r for r in run(month=7)["results"]}["tstv"]
    assert valley["access"] == "no_road" and "Boat only." in valley["warnings"]


# ---------- scoring ----------

def test_scenery_and_wildlife_change_the_ranking():
    assert codes(run(month=7, scenery=("canyons",)))[0] == "tstv"
    assert codes(run(month=7, scenery=("mountains",), wildlife=("elk",)))[0] == "tstp"


def test_skipped_preferences_drop_out_of_the_weights():
    result = run(month=7)
    assert result["weights"] == {"weather": 1.0}
    top = result["results"][0]
    assert top["score"] == top["weather"]["score"]
    assert set(top["parts"]) == {"weather"}


def test_weights_renormalise_and_scores_stay_in_range():
    result = run(month=4, origin="Las Vegas, NV", temperature="mild", scenery=("lakes_rivers", "canyons"))
    assert abs(sum(result["weights"].values()) - 1.0) < 1e-3
    for r in result["results"]:
        assert 0 <= r["score"] <= 100
        assert r["reasons"]


def test_temperature_preference_follows_the_season():
    # The warmer test park should fit "warm" better in July than in January.
    july = {r["park_code"]: r for r in run(month=7, temperature="warm")["results"]}
    january = {r["park_code"]: r for r in run(month=1, temperature="warm")["results"]}
    assert july["tstv"]["parts"]["temperature"] > january["tstv"]["parts"]["temperature"]


def test_only_nps_credited_photos_are_returned():
    by_code = {r["park_code"]: r for r in run(month=7)["results"]}
    assert by_code["tstp"]["photo"]["credit"] == "NPS Photo"
    assert by_code["tstv"]["photo"] is None


# ---------- API ----------

def test_options_endpoint(client):
    body = client.get("/api/recommend/options").json()
    assert "Seattle, WA" in body["origins"]
    assert {"key": "mountains", "label": "Mountains & volcanoes"} in body["scenery"]


def test_recommend_endpoint(client):
    response = client.post("/api/recommend/parks", json={"month": 7, "scenery": ["mountains"], "limit": 1})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["considered"] == 2
    assert [r["park_code"] for r in body["results"]] == ["tstp"]


@pytest.mark.parametrize("payload", [
    {"month": 13},
    {"month": 7, "scenery": ["volcano"]},
    {"month": 7, "origin": "Atlantis"},
    {"month": 7, "max_miles": 100},
    {"month": 7, "temperature": "tropical"},
])
def test_recommend_rejects_bad_input(client, payload):
    response = client.post("/api/recommend/parks", json=payload)
    assert response.status_code in (400, 422)
    assert response.json()["error"]["message"]
