"""Build parks.csv, trails.csv, trail_photos.csv and park_photos.csv.

Inputs: the raw NPS API responses saved by fetch_nps_content.py, the curated
route list in config/trail_catalog.json, and (for geometry status only) the
existing data/processed/trail_routes.geojson. Nothing is invented: text,
coordinates, and photos come from the API records; distances, gains, and
times come from the curated config, which names its source.
"""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parkmatch.catalog import (  # noqa: E402
    derive_difficulty,
    load_catalog,
    validate_catalog,
)


RAW_DIR = ROOT / "data" / "raw" / "nps_api"
PROCESSED_DIR = ROOT / "data" / "processed"
CONFIG = ROOT / "config" / "trail_catalog.json"
DESCRIPTION_MAX_CHARS = 700
NPS_CREDIT = re.compile(r"^\s*nps\s+photo", re.IGNORECASE)


def clean_text(value: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([.,;:!?])", r"\1", text)


def split_sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?])\s+", text) if part]


def shorten(text: str, limit: int) -> str:
    kept: list[str] = []
    length = 0
    for sentence in split_sentences(text):
        if kept and length + len(sentence) > limit:
            break
        kept.append(sentence)
        length += len(sentence) + 1
    return " ".join(kept)


def load_raw(name: str) -> list[dict]:
    path = RAW_DIR / f"{name}_mora.json"
    return json.loads(path.read_text(encoding="utf-8"))["data"]


def license_for(credit: str) -> str:
    """NPS staff photos are U.S. government works; anything else is unknown."""
    return "public_domain" if NPS_CREDIT.match(credit or "") else "unknown"


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {path.relative_to(ROOT)}")


def main() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    park_code = config["park_code"]
    things = {record["title"]: record for record in load_raw("thingstodo")}
    places = {record["title"]: record for record in load_raw("places")}
    park = load_raw("parks")[0]

    routes_path = PROCESSED_DIR / "trail_routes.geojson"
    route_status: dict[str, dict] = {}
    if routes_path.exists():
        for feature in json.loads(routes_path.read_text(encoding="utf-8"))["features"]:
            route_status[feature["properties"]["trail_id"]] = feature["properties"]

    # --- parks.csv -------------------------------------------------------
    fees = "; ".join(
        f"{fee['title']}: ${float(fee['cost']):.0f}" for fee in park["entranceFees"][:3]
    )
    write_csv(
        PROCESSED_DIR / "parks.csv",
        [
            "park_code",
            "park_name",
            "latitude",
            "longitude",
            "description",
            "official_url",
            "conditions_url",
            "entrance_fee_note",
        ],
        [
            {
                "park_code": park_code,
                "park_name": park["fullName"],
                "latitude": park["latitude"],
                "longitude": park["longitude"],
                "description": clean_text(park["description"]),
                "official_url": park["url"],
                "conditions_url": park["url"].replace(
                    "index.htm", "planyourvisit/conditions.htm"
                ),
                "entrance_fee_note": fees,
            }
        ],
    )

    # --- park_photos.csv -------------------------------------------------
    park_photos = [
        {
            "park_code": park_code,
            "title": image["title"],
            "remote_url": image["url"],
            "alt_text": image["altText"],
            "credit": image["credit"],
            "license_type": license_for(image["credit"]),
            "is_hero": str(image["title"] == config["hero_photo_title"]).lower(),
        }
        for image in park["images"]
    ]
    write_csv(
        PROCESSED_DIR / "park_photos.csv",
        list(park_photos[0].keys()),
        park_photos,
    )

    # --- trails.csv and trail_photos.csv ---------------------------------
    trail_rows: list[dict] = []
    photo_rows: list[dict] = []
    for entry in config["trails"]:
        trail_id = entry["trail_id"]
        record = things[entry["nps_title"]]
        long_text = clean_text(record["longDescription"])

        alerts = [s for s in split_sentences(long_text) if "CLOSED" in s]
        body = long_text.split("Trail Statistics")[0]
        anchor = entry.get("description_anchor")
        if anchor and anchor in body:
            body = body[body.index(anchor):]
        body = " ".join(s for s in split_sentences(body) if s not in alerts)

        latitude, longitude = record["latitude"], record["longitude"]
        if entry.get("trailhead_place"):
            place = places[entry["trailhead_place"]]
            latitude, longitude = place["latitude"], place["longitude"]

        status = route_status.get(trail_id)
        trail_rows.append(
            {
                "trail_id": trail_id,
                "park_code": park_code,
                "trail_name": entry["trail_name"],
                "area": entry["area"],
                "distance_miles": entry["distance_miles"],
                "elevation_gain_ft": entry["elevation_gain_ft"],
                "estimated_hours": entry["estimated_hours"],
                "nps_duration_text": entry.get("nps_duration_text")
                or record["duration"],
                "difficulty": derive_difficulty(
                    entry["distance_miles"], entry["elevation_gain_ft"]
                ),
                "route_type": entry["route_type"],
                "scenery_tags": "|".join(entry["scenery_tags"]),
                "designation": entry.get("designation"),
                "latitude": latitude,
                "longitude": longitude,
                "summary": entry.get("summary")
                or clean_text(record["shortDescription"]),
                "description": shorten(body, DESCRIPTION_MAX_CHARS),
                "alert": " ".join(alerts[:2]),
                "seasons": "|".join(record["season"]),
                "source_url": record["url"],
                "last_verified": config["last_verified"],
                "geometry_verified": str(
                    bool(status and status.get("geometry_verified"))
                ).lower(),
                "geometry_status": status["validation_status"] if status else "none",
                "attribute_note": entry.get("attribute_note"),
            }
        )

        sources = [(record["images"][0], record["url"], None)]
        for title in entry["photo_places"]:
            place = places[title]
            if place["images"]:
                sources.append((place["images"][0], place["url"], place))

        cover_assigned = False
        for order, (image, source_url, place) in enumerate(sources, start=1):
            license_type = license_for(image["credit"])
            approved = license_type != "unknown"
            is_cover = approved and not cover_assigned
            cover_assigned = cover_assigned or is_cover
            photo_rows.append(
                {
                    "photo_id": f"{trail_id}_{order:02d}",
                    "trail_id": trail_id,
                    "remote_url": image["url"],
                    "local_path": "",
                    "sort_order": order,
                    "is_cover": str(is_cover).lower(),
                    "alt_text": image["altText"],
                    "caption": image.get("caption") or image.get("title") or "",
                    "credit": image["credit"],
                    "source_url": source_url,
                    "license_type": license_type,
                    "license_url": "",
                    "review_status": "approved" if approved else "candidate",
                    "width": "",
                    "height": "",
                    "retrieved_date": config["last_verified"],
                    "lat": place["latitude"] if place else "",
                    "lon": place["longitude"] if place else "",
                }
            )

    write_csv(PROCESSED_DIR / "trails.csv", list(trail_rows[0].keys()), trail_rows)
    write_csv(
        PROCESSED_DIR / "trail_photos.csv", list(photo_rows[0].keys()), photo_rows
    )

    problems = validate_catalog(load_catalog(PROCESSED_DIR))
    if problems:
        raise SystemExit("Catalog problems:\n- " + "\n- ".join(problems))
    print("Catalog joins are valid.")


if __name__ == "__main__":
    main()
