"""
Phase 2 park loader: the U.S. National Parks from the NPS API into the `parks` table.

Usage, from the backend/ folder (needs NPS_API_KEY in .env):
    python -m scripts.load_parks

Which parks
    The NPS lists ~475 units (monuments, historic sites, trails...). We keep the ones
    whose designation contains "National Park" (this also covers "National Park &
    Preserve" and "National Parks"), plus two National Parks whose designation field
    says something else: American Samoa (blank) and Redwood ("National and State Parks").
    Sequoia and Kings Canyon share one NPS code, `seki`, so they are one row.

Which point the weather describes
    The NPS park coordinates are a geographic centre, which for big parks can be
    roadless wilderness. Visitors care about the places they actually go, so each
    park's weather point is an NPS visitor center:
      1. an explicit choice from PREFERRED_VISITOR_CENTER, where the nearest one is
         the wrong pick (e.g. Denali's busy entrance area, not a remote station);
      2. otherwise the visitor center nearest the park centre, if it is within
         MAX_VISITOR_CENTER_KM (centres outside the park, like Kotzebue for Kobuk
         Valley, are skipped);
      3. otherwise the NPS park centre itself.
    `weather_location_note` records which one was used.

Re-running is safe: rows are upserted by park_code. The three Phase 1 dev-seed parks
are replaced by their official NPS records.
"""

import argparse
import logging
import math
import sys

import requests

from app.config import get_settings
from app.database.connection import SessionLocal, init_db
from app.database.models import Park
from app.database.upsert import upsert_rows
from scripts.http_client import get_json

logger = logging.getLogger("parkwise.etl.parks")

NPS_BASE_URL = "https://developer.nps.gov/api/v1"

# National Parks whose NPS `designation` field doesn't contain "National Park".
EXTRA_NATIONAL_PARKS = {"npsa", "redw"}

# park_code -> text that identifies the preferred visitor center by name.
PREFERRED_VISITOR_CENTER = {
    "dena": "Denali Visitor Center",       # entrance area, where most visitors are
    "drto": "Garden Key",                  # on Fort Jefferson, not Key West
    "gaar": "Anaktuvuk Pass",              # the only one inside the park
    "glac": "Apgar",                       # open all year; Logan Pass is snowed in most of it
    "glba": "Glacier Bay National Park Visitor Center",  # Bartlett Cove; the centre is open water
    "grca": "Grand Canyon Visitor Center",  # South Rim main visitor center
    "isro": "Rock Harbor",                 # on the island, not Houghton (mainland)
    "mora": "Henry M Jackson",             # Paradise, the most visited area
    "npsa": "Visitor Center and Park Store",  # Pago Pago; the NPS centre point is off Tutuila
    "romo": "Beaver Meadows",              # main east entrance
    "seki": "Giant Forest",                # the sequoia groves most visitors come for
    "yell": "Old Faithful",                # the most visited area
    "yose": "Yosemite Valley",             # the most visited area
    "zion": "Zion Canyon Visitor Center",  # main visitor center
}

MAX_VISITOR_CENTER_KM = 60.0


def is_national_park(nps_park: dict) -> bool:
    return "National Park" in (nps_park.get("designation") or "") or (
        nps_park.get("parkCode") in EXTRA_NATIONAL_PARKS
    )


def _coords(record: dict) -> tuple[float, float] | None:
    try:
        lat, lon = float(record["latitude"]), float(record["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    if lat == 0 and lon == 0:  # NPS uses empty strings or 0 for "unknown"
        return None
    return lat, lon


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle (haversine) distance between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def choose_weather_point(nps_park: dict, visitor_centers: list[dict]) -> tuple[float, float, str]:
    """Return (latitude, longitude, note) for the point whose weather represents the park."""
    centre = _coords(nps_park)
    candidates = [(vc, _coords(vc)) for vc in visitor_centers]
    candidates = [(vc, xy) for vc, xy in candidates if xy is not None]

    preferred = PREFERRED_VISITOR_CENTER.get(nps_park["parkCode"])
    if preferred:
        for vc, xy in candidates:
            if preferred.lower() in vc["name"].lower():
                return xy[0], xy[1], f"Weather point: {vc['name']} (NPS visitor center)."

    if centre and candidates:
        vc, xy = min(candidates, key=lambda c: distance_km(centre, c[1]))
        if distance_km(centre, xy) <= MAX_VISITOR_CENTER_KM:
            return xy[0], xy[1], f"Weather point: {vc['name']} (NPS visitor center)."

    if centre is None:
        raise ValueError(f"No usable coordinates for {nps_park['parkCode']}")
    return centre[0], centre[1], (
        "Weather point: NPS park centre coordinates (no visitor center inside the park). "
        "Conditions vary a lot across the park."
    )


def fetch_all(session: requests.Session, endpoint: str, api_key: str) -> list[dict]:
    """Fetch every record from a paginated NPS endpoint."""
    records: list[dict] = []
    start = 0
    while True:
        page = get_json(
            session,
            f"{NPS_BASE_URL}/{endpoint}",
            params={"limit": 500, "start": start},
            headers={"X-Api-Key": api_key},
        )
        records.extend(page["data"])
        start += len(page["data"])
        if not page["data"] or start >= int(page["total"]):
            return records


def build_park_rows(nps_parks: list[dict], visitor_centers: list[dict]) -> list[dict]:
    centers_by_park: dict[str, list[dict]] = {}
    for vc in visitor_centers:
        centers_by_park.setdefault(vc.get("parkCode", ""), []).append(vc)

    rows = []
    for park in sorted(filter(is_national_park, nps_parks), key=lambda p: p["parkCode"]):
        lat, lon, note = choose_weather_point(park, centers_by_park.get(park["parkCode"], []))
        rows.append(
            {
                "park_code": park["parkCode"].lower(),
                "park_name": park["fullName"].strip(),
                "state": park["states"],
                "latitude": round(lat, 5),
                "longitude": round(lon, 5),
                "description": (park.get("description") or "").strip() or None,
                "weather_location_note": note,
                "data_source": "nps_api",
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    api_key = get_settings().nps_api_key
    if not api_key:
        logger.error("NPS_API_KEY is empty. Add it to .env (free key: nps.gov/subjects/developer).")
        return 1

    with requests.Session() as session:
        logger.info("Fetching parks and visitor centers from the NPS API")
        nps_parks = fetch_all(session, "parks", api_key)
        visitor_centers = fetch_all(session, "visitorcenters", api_key)
    logger.info("NPS returned %d park units and %d visitor centers", len(nps_parks), len(visitor_centers))

    rows = build_park_rows(nps_parks, visitor_centers)

    init_db()
    with SessionLocal() as db:
        upsert_rows(db, Park, rows, ["park_code"])
        db.commit()

    fallback = [r["park_code"] for r in rows if "park centre" in r["weather_location_note"]]
    print(f"Loaded {len(rows)} National Parks into the parks table.")
    print(f"Weather point is the park centre (no visitor center nearby) for: {', '.join(fallback) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
