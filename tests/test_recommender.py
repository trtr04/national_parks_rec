from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parkmatch.catalog import (  # noqa: E402
    derive_difficulty,
    load_catalog,
    validate_catalog,
)
from parkmatch.recommender import Preferences, recommend  # noqa: E402


def trail(trail_id: str, difficulty, hours, tags=()) -> dict:
    return {
        "trail_id": trail_id,
        "difficulty": difficulty,
        "estimated_hours": hours,
        "scenery_tags": list(tags),
    }


TRAILS = [
    trail("EASY_SHORT", "Easy", 1.0, ["forests"]),
    trail("MOD_LAKE", "Moderate", 2.0, ["lakes", "mountain_views"]),
    trail("MOD_LONG", "Moderate", 3.5, ["waterfalls"]),
    trail("HARD_LONG", "Hard", 6.0, ["mountain_views"]),
]


def test_difficulty_rule_boundaries() -> None:
    assert derive_difficulty(1.2, 200) == "Easy"
    assert derive_difficulty(3.0, 500) == "Moderate"  # gain must be under 500
    assert derive_difficulty(3.1, 100) == "Moderate"
    assert derive_difficulty(8.0, 100) == "Hard"
    assert derive_difficulty(2.0, 2000) == "Hard"
    assert derive_difficulty(None, 300) is None
    assert derive_difficulty(2.0, None) is None


def test_harder_and_longer_trails_are_excluded() -> None:
    result = recommend(TRAILS, Preferences("Moderate", "up_to_2"))
    ids = [rec.trail_id for rec in result.recommendations]
    assert ids == ["MOD_LAKE", "EASY_SHORT"]
    assert "HARD_LONG" in result.excluded
    assert "MOD_LONG" in result.excluded


def test_time_limit_is_inclusive() -> None:
    result = recommend(TRAILS, Preferences("Moderate", "up_to_2"))
    assert "MOD_LAKE" not in result.excluded  # exactly 2 hours


def test_missing_values_never_qualify() -> None:
    trails = [trail("NO_HOURS", "Easy", None), trail("NO_LEVEL", None, 1.0)]
    result = recommend(trails, Preferences("Hard", "over_4"))
    assert result.recommendations == []
    assert set(result.excluded) == {"NO_HOURS", "NO_LEVEL"}


def test_scenery_changes_the_ranking() -> None:
    lakes = recommend(TRAILS, Preferences("Hard", "over_4", ("lakes",)))
    falls = recommend(TRAILS, Preferences("Hard", "over_4", ("waterfalls",)))
    assert lakes.recommendations[0].trail_id != falls.recommendations[0].trail_id
    assert falls.recommendations[0].components["scenery"] == 1.0


def test_results_are_capped_scored_and_repeatable() -> None:
    preferences = Preferences("Hard", "over_4", ("mountain_views",))
    first = recommend(TRAILS, preferences)
    second = recommend(TRAILS, preferences)
    assert len(first.recommendations) == 3
    assert first == second
    assert first.recommendations[0].trail_id == "HARD_LONG"
    assert first.recommendations[0].score == 1.0
    assert all(0.0 <= rec.score <= 1.0 for rec in first.recommendations)
    assert all(rec.reasons for rec in first.recommendations)


def test_no_match_returns_nothing() -> None:
    result = recommend([trail("HARD_LONG", "Hard", 6.0)], Preferences("Easy", "up_to_2"))
    assert result.recommendations == []
    assert result.excluded["HARD_LONG"].startswith("Rated Hard")


def test_built_catalog_joins_and_photo_rules() -> None:
    catalog = load_catalog(ROOT / "data" / "processed")
    assert validate_catalog(catalog) == []
    assert len(catalog.trails) >= 3
    for item in catalog.trails:
        photos = catalog.showable_photos(item["trail_id"])
        assert len(photos) <= 3
        assert all(photo["license_type"] != "unknown" for photo in photos)
        assert all(photo["review_status"] == "approved" for photo in photos)


def test_every_trail_has_one_connected_provisional_route() -> None:
    catalog = load_catalog(ROOT / "data" / "processed")
    for item in catalog.trails:
        properties = catalog.routes[item["trail_id"]]["properties"]
        assert properties["connected_component_count"] == 1
        assert properties["geometry_verified"] is False
        assert properties["source_objectids"]
