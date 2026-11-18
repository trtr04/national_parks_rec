"""
Phase 1 development seed: three parks, so the website has something to show
before the NPS API pipeline exists.

Usage, from the backend/ folder:
    python -m scripts.seed_dev_parks

What this is and isn't
    * Only park reference points (name, state, coordinates). No weather data is created —
      weather comes only from Open-Meteo, via the Phase 2 ETL.
    * Coordinates are each park's main visitor center, chosen as a representative,
      visitor-accessible weather point. Rows are tagged data_source='dev_seed'.
    * The Phase 2 NPS loader upserts by park_code, so these rows get replaced by
      official NPS records automatically.
"""

from app.database.connection import SessionLocal, init_db
from app.database.models import Park

DEV_PARKS = [
    {
        "park_code": "yose",
        "park_name": "Yosemite National Park",
        "state": "CA",
        "latitude": 37.7486,
        "longitude": -119.5871,
        "weather_location_note": (
            "Yosemite Valley Visitor Center (~1,200 m). High country such as Tuolumne "
            "Meadows (~2,600 m) is typically much colder and snowier."
        ),
    },
    {
        "park_code": "grca",
        "park_name": "Grand Canyon National Park",
        "state": "AZ",
        "latitude": 36.0590,
        "longitude": -112.1092,
        "weather_location_note": (
            "South Rim, Grand Canyon Visitor Center (~2,100 m). The canyon floor is "
            "far hotter; the North Rim is higher and closes in winter."
        ),
    },
    {
        "park_code": "zion",
        "park_name": "Zion National Park",
        "state": "UT",
        "latitude": 37.2002,
        "longitude": -112.9869,
        "weather_location_note": (
            "Zion Canyon Visitor Center (~1,200 m). Kolob Canyons and plateau trails "
            "sit higher and run cooler."
        ),
    },
]


def main() -> None:
    init_db()
    with SessionLocal() as db:
        for data in DEV_PARKS:
            # merge() = insert or update by primary key, so re-running never duplicates.
            db.merge(Park(**data, data_source="dev_seed"))
        db.commit()
    print(f"Seeded {len(DEV_PARKS)} development parks: {', '.join(p['park_code'] for p in DEV_PARKS)}")


if __name__ == "__main__":
    main()
