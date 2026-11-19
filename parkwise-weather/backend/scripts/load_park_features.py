"""
Load what each National Park offers into the `park_features` table.

Usage, from the backend/ folder (needs NPS_API_KEY in .env; run load_parks first):
    python -m scripts.load_park_features
    python -m scripts.load_park_features --save-dir raw/   # also keep the API responses
    python -m scripts.load_park_features --from-dir raw/   # reuse saved responses, fetch the rest

The free NPS key allows about 1,000 requests an hour (the DEMO_KEY only 10), so saving
the responses makes re-runs cheap. If visitor centers can't be fetched, their count is
stored as unknown (NULL) and the recommender doesn't filter on it.

Sources (NPS Data API, https://www.nps.gov/subjects/developer/api-documentation.htm)
    /parks           topics, activities, entrance fees, park URL, first photo
    /campgrounds     how many campgrounds each park lists, how many have showers, and in
                 which months each is open (from its listed seasonal closures)
    /visitorcenters  how many visitor centers each park lists

Topics and activities are saved with NPS's own names. Mapping them to the scenery and
wildlife choices users see happens in app/services/park_recommender.py, so the mapping
can be tuned without reloading. Only parks already in the `parks` table get a row.

Re-running is safe: rows are upserted by park_code.
"""

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path

import requests
from sqlalchemy import select

from app.config import get_settings
from app.database.connection import SessionLocal, init_db
from app.database.models import Park, ParkFeatures
from app.database.upsert import upsert_rows
from scripts.http_client import RateLimitedError
from scripts.load_parks import fetch_all

logger = logging.getLogger("parkwise.etl.features")

VEHICLE_FEE_TITLE = "Entrance - Private Vehicle"


def _has_showers(campground: dict) -> bool:
    showers = (campground.get("amenities") or {}).get("showers") or []
    return any(value and value.strip().lower() != "none" for value in showers)


# A campground counts as open in a month unless listed closures cover at least this
# share of the month's days.
CLOSED_SHARE_OF_MONTH = 0.5


def _all_closed(hours: dict) -> bool:
    values = [v for v in (hours or {}).values() if v]
    return bool(values) and all(v.strip().lower() == "closed" for v in values)


def open_months(campground: dict) -> list[bool]:
    """
    Twelve booleans, January first: is the campground open for most of each month?

    Uses the "exceptions" in NPS operatingHours whose hours are all "Closed" (for example
    "Closed Seasonally, 2026-10-12 to 2027-05-23"). Dates are folded onto the calendar,
    ignoring the year, so a closure listed for this winter stands for every winter.
    Standard hours that are all "Closed" mean closed all year. No listed closure: open.
    """
    hours = campground.get("operatingHours") or []
    if hours and all(_all_closed(h.get("standardHours")) for h in hours):
        return [False] * 12

    closed_days: set[tuple[int, int]] = set()
    for block in hours:
        for exc in block.get("exceptions") or []:
            if not _all_closed(exc.get("exceptionHours")):
                continue
            try:
                start = dt.date.fromisoformat(exc["startDate"])
                end = dt.date.fromisoformat(exc["endDate"])
            except (KeyError, TypeError, ValueError):
                continue
            if end < start or (end - start).days > 366:
                continue
            day = start
            while day <= end:
                closed_days.add((day.month, day.day))
                day += dt.timedelta(days=1)

    result = []
    for month in range(1, 13):
        days_in_month = (dt.date(2001 + month // 12, month % 12 + 1, 1) - dt.date(2001, month, 1)).days
        closed = sum(1 for m, _d in closed_days if m == month)
        result.append(closed < CLOSED_SHARE_OF_MONTH * days_in_month)
    return result


def _vehicle_fee(nps_park: dict) -> float | None:
    for fee in nps_park.get("entranceFees") or []:
        if (fee.get("title") or "").strip() == VEHICLE_FEE_TITLE:
            try:
                return float(fee["cost"])
            except (KeyError, TypeError, ValueError):
                return None
    return None


def build_feature_rows(
    nps_parks: list[dict],
    campgrounds: list[dict],
    visitor_centers: list[dict] | None,
    park_codes: set[str],
) -> list[dict]:
    """One row per park in `park_codes`, from raw NPS API records."""
    camp_count: dict[str, int] = {}
    shower_count: dict[str, int] = {}
    open_count: dict[str, list[int]] = {}
    for camp in campgrounds:
        code = (camp.get("parkCode") or "").lower()
        camp_count[code] = camp_count.get(code, 0) + 1
        counts = open_count.setdefault(code, [0] * 12)
        for i, is_open in enumerate(open_months(camp)):
            counts[i] += int(is_open)
        if _has_showers(camp):
            shower_count[code] = shower_count.get(code, 0) + 1

    vc_count: dict[str, int] = {}
    for vc in visitor_centers or []:
        code = (vc.get("parkCode") or "").lower()
        vc_count[code] = vc_count.get(code, 0) + 1

    rows = []
    for park in nps_parks:
        code = park["parkCode"].lower()
        if code not in park_codes:
            continue
        image = (park.get("images") or [{}])[0]
        rows.append({
            "park_code": code,
            "topics": sorted({t["name"] for t in park.get("topics") or []}),
            "activities": sorted({a["name"] for a in park.get("activities") or []}),
            "campground_count": camp_count.get(code, 0),
            "campgrounds_with_showers": shower_count.get(code, 0),
            "campground_open_months": open_count.get(code, [0] * 12),
            "visitor_center_count": vc_count.get(code, 0) if visitor_centers is not None else None,
            "vehicle_fee_usd": _vehicle_fee(park),
            "nps_url": park.get("url") or None,
            "image_url": image.get("url") or None,
            "image_alt": image.get("altText") or None,
            "image_credit": image.get("credit") or None,
        })
    return sorted(rows, key=lambda r: r["park_code"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--from-dir", type=Path, help="Read <endpoint>.json here when present")
    parser.add_argument("--save-dir", type=Path, help="Save each fetched API response here")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    api_key = get_settings().nps_api_key
    if not api_key:
        logger.error("NPS_API_KEY is empty. Add it to .env (free key: nps.gov/subjects/developer).")
        return 1

    init_db()
    with SessionLocal() as db:
        park_codes = set(db.scalars(select(Park.park_code)))
    if not park_codes:
        logger.error("The parks table is empty. Run `python -m scripts.load_parks` first.")
        return 1

    def load(session: requests.Session, endpoint: str) -> list[dict]:
        saved = args.from_dir / f"{endpoint}.json" if args.from_dir else None
        if saved and saved.exists():
            logger.info("Reading %s", saved)
            payload = json.loads(saved.read_text(encoding="utf-8"))
            return payload["data"] if isinstance(payload, dict) else payload
        logger.info("Fetching %s from the NPS API", endpoint)
        records = fetch_all(session, endpoint, api_key)
        if args.save_dir:
            args.save_dir.mkdir(parents=True, exist_ok=True)
            (args.save_dir / f"{endpoint}.json").write_text(json.dumps({"data": records}), encoding="utf-8")
        return records

    with requests.Session() as session:
        nps_parks = load(session, "parks")
        campgrounds = load(session, "campgrounds")
        try:
            visitor_centers = load(session, "visitorcenters")
        except RateLimitedError:
            logger.warning("Rate limited on visitor centers; their count is stored as unknown. Re-run later.")
            visitor_centers = None

    rows = build_feature_rows(nps_parks, campgrounds, visitor_centers, park_codes)
    with SessionLocal() as db:
        upsert_rows(db, ParkFeatures, rows, ["park_code"])
        db.commit()

    missing = sorted(park_codes - {r["park_code"] for r in rows})
    print(f"Loaded features for {len(rows)} of {len(park_codes)} parks.")
    if missing:
        print(f"No NPS record found for: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
