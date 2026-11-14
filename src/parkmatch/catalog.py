"""Load and check the curated ParkMatch tables (parks, trails, photos, routes)."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DIFFICULTY_LEVELS = ("Easy", "Moderate", "Hard")
SCENERY_TAGS = ("mountain_views", "waterfalls", "lakes", "forests", "wildflowers")
SHOWABLE_LICENSES = ("public_domain", "cc_by", "permission")

# Documented difficulty rule (draft, see PRD section 11).
EASY_MAX_MILES = 3.0
EASY_MAX_GAIN_FT = 500  # exclusive
HARD_MIN_MILES = 8.0
HARD_MIN_GAIN_FT = 2000


def derive_difficulty(
    distance_miles: float | None, elevation_gain_ft: float | None
) -> str | None:
    """Label a route from its full distance and total ascent.

    Hard: at least 8 miles or at least 2,000 ft of gain.
    Easy: at most 3 miles and under 500 ft of gain.
    Moderate: everything else. Unknown inputs give no label.
    """
    if distance_miles is None or elevation_gain_ft is None:
        return None
    if distance_miles >= HARD_MIN_MILES or elevation_gain_ft >= HARD_MIN_GAIN_FT:
        return "Hard"
    if distance_miles <= EASY_MAX_MILES and elevation_gain_ft < EASY_MAX_GAIN_FT:
        return "Easy"
    return "Moderate"


def _float_or_none(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    return float(value)


def _text_or_none(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    return value.strip()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@dataclass
class Catalog:
    parks: dict[str, dict[str, Any]]
    trails: list[dict[str, Any]]
    photos: list[dict[str, Any]]
    park_photos: list[dict[str, Any]]
    routes: dict[str, dict[str, Any]]  # trail_id -> GeoJSON feature

    def trail(self, trail_id: str) -> dict[str, Any]:
        for trail in self.trails:
            if trail["trail_id"] == trail_id:
                return trail
        raise KeyError(trail_id)

    def showable_photos(self, trail_id: str, limit: int = 3) -> list[dict[str, Any]]:
        """Approved photos with a known license, cover first, at most ``limit``."""
        photos = [
            photo
            for photo in self.photos
            if photo["trail_id"] == trail_id
            and photo["review_status"] == "approved"
            and photo["license_type"] in SHOWABLE_LICENSES
        ]
        photos.sort(key=lambda photo: (not photo["is_cover"], photo["sort_order"]))
        return photos[:limit]


def load_catalog(processed_dir: Path) -> Catalog:
    parks = {}
    for row in _read_csv(processed_dir / "parks.csv"):
        row["latitude"] = _float_or_none(row["latitude"])
        row["longitude"] = _float_or_none(row["longitude"])
        parks[row["park_code"]] = row

    trails = []
    for row in _read_csv(processed_dir / "trails.csv"):
        trail: dict[str, Any] = dict(row)
        for field in (
            "distance_miles",
            "elevation_gain_ft",
            "estimated_hours",
            "latitude",
            "longitude",
        ):
            trail[field] = _float_or_none(row[field])
        for field in (
            "difficulty",
            "route_type",
            "designation",
            "alert",
            "attribute_note",
            "nps_duration_text",
        ):
            trail[field] = _text_or_none(row[field])
        trail["scenery_tags"] = [
            tag for tag in row["scenery_tags"].split("|") if tag
        ]
        trail["geometry_verified"] = row["geometry_verified"].lower() == "true"
        trails.append(trail)

    photos = []
    for row in _read_csv(processed_dir / "trail_photos.csv"):
        photo: dict[str, Any] = dict(row)
        photo["sort_order"] = int(row["sort_order"])
        photo["is_cover"] = row["is_cover"].lower() == "true"
        photos.append(photo)

    park_photos_path = processed_dir / "park_photos.csv"
    park_photos = _read_csv(park_photos_path) if park_photos_path.exists() else []

    routes = {}
    routes_path = processed_dir / "trail_routes.geojson"
    if routes_path.exists():
        collection = json.loads(routes_path.read_text(encoding="utf-8"))
        for feature in collection["features"]:
            routes[feature["properties"]["trail_id"]] = feature

    return Catalog(parks, trails, photos, park_photos, routes)


def validate_catalog(catalog: Catalog) -> list[str]:
    """Return a list of problems; an empty list means every join holds."""
    problems: list[str] = []
    trail_ids = [trail["trail_id"] for trail in catalog.trails]
    if len(trail_ids) != len(set(trail_ids)):
        problems.append("trails.csv has duplicate trail_id values")
    known = set(trail_ids)

    for trail in catalog.trails:
        trail_id = trail["trail_id"]
        if trail["park_code"] not in catalog.parks:
            problems.append(f"{trail_id}: park_code not in parks.csv")
        if trail["difficulty"] not in (*DIFFICULTY_LEVELS, None):
            problems.append(f"{trail_id}: unknown difficulty {trail['difficulty']!r}")
        unknown_tags = set(trail["scenery_tags"]) - set(SCENERY_TAGS)
        if unknown_tags:
            problems.append(f"{trail_id}: unknown scenery tags {sorted(unknown_tags)}")
        if trail["geometry_verified"] and trail_id not in catalog.routes:
            problems.append(f"{trail_id}: geometry_verified but no route feature")

    for trail_id in catalog.routes:
        if trail_id not in known:
            problems.append(f"trail_routes.geojson: {trail_id} not in trails.csv")

    photo_ids = [photo["photo_id"] for photo in catalog.photos]
    if len(photo_ids) != len(set(photo_ids)):
        problems.append("trail_photos.csv has duplicate photo_id values")
    covers: dict[str, int] = {}
    for photo in catalog.photos:
        if photo["trail_id"] not in known:
            problems.append(f"{photo['photo_id']}: trail_id not in trails.csv")
        if photo["is_cover"]:
            covers[photo["trail_id"]] = covers.get(photo["trail_id"], 0) + 1
            if photo["review_status"] != "approved":
                problems.append(f"{photo['photo_id']}: cover photo is not approved")
    for trail_id, count in covers.items():
        if count > 1:
            problems.append(f"{trail_id}: more than one cover photo")
    return problems
