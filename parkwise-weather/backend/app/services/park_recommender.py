"""
Park recommender: rank National Parks for a traveller's month, activity and preferences.

How a park is chosen
    1. Filters. A park is left out if it is farther than the traveller's maximum distance,
       lacks a must-have amenity, or doesn't offer the chosen activity (hiking needs the NPS
       "Hiking" activity, camping needs at least one campground, wildlife watching needs
       "Wildlife Watching"). Every left-out park gets a reason.
    2. Score (0–100). A weighted average of the parts the traveller cares about:

           weather      always   the month's suitability score for the activity, from the
                                 ParkWise climate model (same numbers as /best-time)
           temperature  if set   how close the month's typical high is to the chosen band
           scenery      if set   share of the chosen scenery types the park has
           wildlife     if set   share of the chosen animals NPS lists for the park
           distance     if set   closer is better, measured in a straight line

       Parts the traveller skipped are left out and the weights re-normalised, so a skipped
       preference never counts against a park.
    3. Reasons. Each result says in plain words why it matched.

Scenery and wildlife come from the NPS park "topics". These describe what each park
interprets, which is not always what visitors see: wildlife in particular is thin (no
bears, moose or mountain goats are tagged anywhere). The labels say so on screen.
Distances are straight-line ("as the crow flies"), not driving distances.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Park, ParkFeatures
from app.models.schemas import Activity
from app.services import model_store
from app.services.climate_models import add_features
from app.services.errors import ParkWiseError
from app.services.suitability import label_for, score_day

# ---------- Choices offered to users ----------

# key -> (label, NPS topic names that count as a match)
SCENERY = {
    "mountains": ("Mountains & volcanoes", {"Mountains", "Volcanoes"}),
    "glaciers": ("Glaciers", {"Glaciers"}),
    "lakes_rivers": ("Lakes & rivers", {"Lakes", "River and Riparian", "Water Trails"}),
    "waterfalls": ("Waterfalls", {"Waterfalls"}),
    "forests": ("Forests", {"Forests and Woodlands", "Coniferous Forests", "Deciduous Forests", "Rainforest"}),
    "canyons": ("Canyons & rock formations", {"Canyons and Canyonlands", "Rock Landscapes and Features",
                                              "Arches", "Plateaus and Mesas", "Buttes"}),
    "dunes": ("Sand dunes", {"Dunes"}),
    "coasts": ("Coasts & islands", {"Oceans", "Coasts, Islands and Atolls", "Coral Reefs",
                                     "Estuaries and Mangroves"}),
    "meadows": ("Meadows & grasslands", {"Meadows", "Grasslands", "Prairies", "Tundra"}),
    "geothermal": ("Hot springs & geysers", {"Geothermal", "Hot Springs", "Geysers"}),
    "caves": ("Caves", {"Caves, Caverns and Karst"}),
    "night_sky": ("Dark night skies", {"Night Sky", "Astronomy", "Aurora Borealis"}),
    "fossils": ("Fossils", {"Fossils and Paleontology", "Dinosaur", "Petrified Wood"}),
}

WILDLIFE = {
    "birds": ("Birds", {"Birds"}),
    "elk": ("Elk", {"Elk"}),
    "bison": ("Bison", {"Bison"}),
    "wolves": ("Wolves", {"Wolves"}),
    "wild_cats": ("Wild cats", {"Cats (wild)"}),
    "whales": ("Whales", {"Whales"}),
    "turtles": ("Sea turtles & tortoises", {"Tortoises and Turtles"}),
    "alligators": ("Alligators & crocodiles", {"Alligators or Crocodiles"}),
    "wild_horses": ("Wild horses", {"Horses (wild)"}),
    "fish": ("Fish", {"Fish"}),
}


def _has_activity(*names: str):
    return lambda f, month: any(name in f.activities for name in names)


def campgrounds_open(features: ParkFeatures, month: int) -> int:
    """How many campgrounds are open for most of `month` (all of them if seasons are unknown)."""
    months = features.campground_open_months
    return months[month - 1] if months else features.campground_count


# Parks with no road in: visitors arrive by small plane or boat (hand-checked list).
NO_ROAD_ACCESS = {
    "chis": "Reached only by boat or small plane from the mainland.",
    "drto": "Reached only by ferry, boat or seaplane from Key West.",
    "gaar": "No roads: reached by small plane (air taxi).",
    "glba": "No road from elsewhere: reached by plane or ferry to Gustavus.",
    "isro": "Reached only by ferry or seaplane.",
    "katm": "No road from elsewhere: reached by small plane to Brooks Camp or King Salmon.",
    "kova": "No roads: reached by small plane from Kotzebue.",
    "lacl": "No roads: reached by small plane.",
}
# Parks on islands away from the mainland: a flight (or ferry) is needed from most cities.
ISLAND_ACCESS = {
    "hale": "On Maui: fly to the island first.",
    "havo": "On Hawaiʻi Island: fly to the island first.",
    "npsa": "In American Samoa: a long flight from Hawaiʻi.",
    "viis": "On St. John: fly to St. Thomas, then take a ferry.",
}

# key -> (label, test on a ParkFeatures row and the travel month)
AMENITIES = {
    "road_access": ("Reachable by car", lambda f, m: f.park_code not in NO_ROAD_ACCESS),
    "campground": ("Campground open that month", lambda f, m: campgrounds_open(f, m) > 0),
    "rv_camping": ("RV camping", _has_activity("RV Camping")),
    "showers": ("Campground with showers", lambda f, m: f.campgrounds_with_showers > 0),
    "food": ("Food in the park", _has_activity("Food", "Dining")),
    # Unknown (not loaded) counts as present, so missing data never excludes a park.
    "visitor_center": ("Visitor center", lambda f, m: f.visitor_center_count is None or f.visitor_center_count > 0),
    "no_vehicle_fee": ("No vehicle entrance fee", lambda f, m: f.vehicle_fee_usd in (None, 0.0)),
}

# What a park must offer for each activity to be considered at all.
ACTIVITY_REQUIREMENT = {
    Activity.hiking: ("hiking", _has_activity("Hiking", "Front-Country Hiking", "Backcountry Hiking")),
    Activity.camping: ("a campground open that month", lambda f, m: campgrounds_open(f, m) > 0),
    Activity.wildlife: ("wildlife watching", _has_activity("Wildlife Watching")),
    Activity.sightseeing: (None, lambda f, m: True),
}

# Comfortable daytime high (°C) for each temperature preference.
TEMPERATURE_BANDS = {
    "cool": ("Cool (about 40–60°F)", (5.0, 16.0)),
    "mild": ("Mild (about 60–75°F)", (16.0, 24.0)),
    "warm": ("Warm (about 72–90°F)", (22.0, 32.0)),
}
POINTS_PER_DEGREE = 6.0  # same slope as the suitability temperature component

# Approximate city-centre coordinates (lat, lon) for the "starting from" choice.
START_CITIES = {
    "Seattle, WA": (47.6062, -122.3321),
    "Spokane, WA": (47.6588, -117.4260),
    "Portland, OR": (45.5152, -122.6784),
    "San Francisco, CA": (37.7749, -122.4194),
    "Los Angeles, CA": (34.0522, -118.2437),
    "San Diego, CA": (32.7157, -117.1611),
    "Las Vegas, NV": (36.1699, -115.1398),
    "Phoenix, AZ": (33.4484, -112.0740),
    "Salt Lake City, UT": (40.7608, -111.8910),
    "Denver, CO": (39.7392, -104.9903),
    "Dallas, TX": (32.7767, -96.7970),
    "Houston, TX": (29.7604, -95.3698),
    "Minneapolis, MN": (44.9778, -93.2650),
    "Chicago, IL": (41.8781, -87.6298),
    "Atlanta, GA": (33.7490, -84.3880),
    "Miami, FL": (25.7617, -80.1918),
    "Washington, DC": (38.9072, -77.0369),
    "New York, NY": (40.7128, -74.0060),
    "Boston, MA": (42.3601, -71.0589),
    "Anchorage, AK": (61.2181, -149.9003),
    "Honolulu, HI": (21.3069, -157.8583),
}

WEIGHTS = {"weather": 0.30, "temperature": 0.15, "scenery": 0.25, "wildlife": 0.10, "distance": 0.20}
# With no maximum set, closeness falls linearly to 0 at this distance.
DISTANCE_SCALE_MILES = 2000.0

PHOTO_MAX_WIDTH = 640

# Parks with a ParkMatch trail guide (Washington pilot).
TRAIL_GUIDE_PARKS = {"mora"}

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]


class FeaturesNotLoadedError(ParkWiseError):
    status_code = 503
    code = "features_not_loaded"


# ---------- Request ----------

@dataclass(frozen=True)
class ParkPreferences:
    month: int
    activity: Activity = Activity.hiking
    origin: str | None = None
    max_miles: float | None = None
    temperature: str | None = None
    scenery: tuple[str, ...] = ()
    wildlife: tuple[str, ...] = ()
    amenities: tuple[str, ...] = ()
    include_poor_weather: bool = False
    limit: int = 6


# ---------- Climate by month, all parks at once ----------

_climate_cache: dict[tuple, pd.DataFrame] = {}


def monthly_climate() -> pd.DataFrame:
    """
    Typical weather and suitability for every park and month, from the trained climate
    model. Same method as weather_service.best_time (a reference year of daily estimates,
    averaged by month), done for all parks in one pass and cached until the model changes.
    Columns: park_code, month, temp_max, temp_min, wet, snow, and one score per activity.
    """
    bundle = model_store.get_bundle()
    key = (id(bundle), bundle.get("trained_at"))
    if key in _climate_cache:
        return _climate_cache[key]

    year = dt.date.today().year + 1
    days = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    frames = [
        pd.DataFrame({"park_code": code, "date": days.date, "latitude": lat, "longitude": lon})
        for code, (lat, lon) in bundle["parks"].items()
    ]
    frame = add_features(pd.concat(frames, ignore_index=True))
    predicted = bundle["model"].predict(frame)
    climatology = bundle["climatology"]
    daily = pd.DataFrame({
        "park_code": frame["park_code"].to_numpy(),
        "month": pd.to_datetime(frame["date"]).dt.month.to_numpy(),
        "temp_max": predicted["temp_max"].to_numpy(),
        "temp_min": predicted[["temp_min", "temp_max"]].min(axis=1).to_numpy(),
        "wet": predicted["wet"].clip(0, 1).to_numpy(),
        "snow": climatology.lookup(frame["park_code"], frame["doy"], "snow_day"),
        "wind": climatology.lookup(frame["park_code"], frame["doy"], "wind_speed_max"),
    })
    for activity in Activity:
        daily[activity.value] = [
            score_day(activity, r.temp_max, r.temp_min, r.wet, r.wind, r.snow)["score"]
            for r in daily.itertuples()
        ]
    monthly = daily.groupby(["park_code", "month"], as_index=False).mean(numeric_only=True)
    _climate_cache.clear()
    _climate_cache[key] = monthly
    return monthly


# ---------- Helpers ----------

def distance_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lon) points, in miles."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 3958.8 * math.asin(math.sqrt(h))


def matched_keys(topics: list[str], choices: dict) -> list[str]:
    """Keys of `choices` whose NPS topics appear in `topics`."""
    present = set(topics)
    return [key for key, (_label, names) in choices.items() if present & names]


def temperature_fit(temp_max_c: float, band: tuple[float, float]) -> float:
    low, high = band
    outside = max(0.0, low - temp_max_c, temp_max_c - high)
    return max(0.0, 100.0 - POINTS_PER_DEGREE * outside)


def _f(celsius: float) -> int:
    return round(celsius * 9 / 5 + 32)


def _labels(keys, choices) -> list[str]:
    return [choices[k][0] for k in keys]


def _join(words: list[str]) -> str:
    words = [w.lower() if i else w for i, w in enumerate(words)]
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def _photo(features: ParkFeatures) -> dict | None:
    """Only NPS-credited photos are shown; others need a rights check first."""
    credit = (features.image_credit or "").strip()
    if not features.image_url or not credit.upper().startswith("NPS"):
        return None
    url = features.image_url
    # nps.gov resizes on request; full-size originals can be several megabytes.
    if url.startswith("https://www.nps.gov/") and "?" not in url:
        url += f"?maxwidth={PHOTO_MAX_WIDTH}"
    return {"url": url, "alt": features.image_alt, "credit": credit}


# ---------- Recommender ----------

def options() -> dict:
    """The choices the frontend offers."""
    as_list = lambda choices: [{"key": k, "label": v[0]} for k, v in choices.items()]  # noqa: E731
    return {
        "activities": [a.value for a in Activity],
        "origins": list(START_CITIES),
        "temperatures": [{"key": k, "label": v[0]} for k, v in TEMPERATURE_BANDS.items()],
        "scenery": as_list(SCENERY),
        "wildlife": as_list(WILDLIFE),
        "amenities": as_list(AMENITIES),
        "weights": WEIGHTS,
        "notes": {
            "distance": "Straight-line distance from the city centre to the park's main visitor area, not driving distance.",
            "scenery": "Scenery and wildlife come from the topics NPS lists for each park, which can miss things visitors see.",
            "score": "Match score: a weighted blend of the parts you chose, 0–100. Parts you skip don't count.",
            "campgrounds": "Campground seasons come from the closure dates NPS lists; check the park before you go.",
        },
    }


def recommend_parks(db: Session, prefs: ParkPreferences) -> dict:
    activity = Activity(prefs.activity)
    rows = db.execute(select(Park, ParkFeatures).join(ParkFeatures, ParkFeatures.park_code == Park.park_code)).all()
    if not rows:
        raise FeaturesNotLoadedError(
            "Park features haven't been loaded yet. From backend/, run `python -m scripts.load_park_features`."
        )

    climate = monthly_climate()
    climate = climate[climate["month"] == prefs.month].set_index("park_code")
    origin_xy = START_CITIES.get(prefs.origin) if prefs.origin else None
    band = TEMPERATURE_BANDS[prefs.temperature][1] if prefs.temperature else None
    need_label, need_test = ACTIVITY_REQUIREMENT[activity]
    month_name = MONTH_NAMES[prefs.month - 1]

    weights = {"weather": WEIGHTS["weather"]}
    if band:
        weights["temperature"] = WEIGHTS["temperature"]
    if prefs.scenery:
        weights["scenery"] = WEIGHTS["scenery"]
    if prefs.wildlife:
        weights["wildlife"] = WEIGHTS["wildlife"]
    if origin_xy:
        weights["distance"] = WEIGHTS["distance"]
    total_weight = sum(weights.values())
    weights = {k: round(w / total_weight, 4) for k, w in weights.items()}

    results, excluded = [], {}
    nearest_beyond = None  # closest park left out only because of the distance limit

    def leave_out(park: Park, reason: str) -> None:
        excluded[park.park_code] = {"park_name": park.park_name, "reason": reason}

    for park, features in rows:
        code = park.park_code
        miles = distance_miles(origin_xy, (park.latitude, park.longitude)) if origin_xy else None

        # 1. Filters, most basic first; distance last so we can name the nearest park left out by it.
        if code not in climate.index:
            leave_out(park, "No climate estimate for this park yet.")
            continue
        if not need_test(features, prefs.month):
            leave_out(park, f"NPS doesn't list {need_label} here.")
            continue
        missing = [AMENITIES[k][0] for k in prefs.amenities if not AMENITIES[k][1](features, prefs.month)]
        if missing:
            leave_out(park, f"Missing: {_join(missing).lower()}.")
            continue
        month = climate.loc[code]
        weather_score = float(month[activity.value])
        weather_label = label_for(weather_score)
        if weather_label == "Poor" and not prefs.include_poor_weather:
            leave_out(park, f"{month_name} weather is poor for {activity.value} (score {weather_score:.0f}).")
            continue
        if prefs.max_miles and miles is not None and miles > prefs.max_miles:
            leave_out(park, f"About {miles:,.0f} miles away, more than your {prefs.max_miles:,.0f}.")
            if nearest_beyond is None or miles < nearest_beyond["distance_miles"]:
                nearest_beyond = {"park_code": code, "park_name": park.park_name, "distance_miles": round(miles)}
            continue

        # 2. Score parts (0–100)
        parts = {"weather": weather_score}
        if band:
            parts["temperature"] = temperature_fit(float(month["temp_max"]), band)
        scenery_all = matched_keys(features.topics, SCENERY)
        scenery_hit = [k for k in prefs.scenery if k in scenery_all]
        if prefs.scenery:
            parts["scenery"] = 100.0 * len(scenery_hit) / len(prefs.scenery)
        wildlife_all = matched_keys(features.topics, WILDLIFE)
        wildlife_hit = [k for k in prefs.wildlife if k in wildlife_all]
        if prefs.wildlife:
            parts["wildlife"] = 100.0 * len(wildlife_hit) / len(prefs.wildlife)
        if origin_xy:
            scale = prefs.max_miles or DISTANCE_SCALE_MILES
            parts["distance"] = max(0.0, 100.0 * (1 - miles / scale))
        score = sum(parts[k] * w for k, w in weights.items())

        # 3. Reasons and warnings
        high, low = float(month["temp_max"]), float(month["temp_min"])
        reasons = [
            f"{month_name} weather is {weather_label.lower()} for {activity.value} "
            f"(score {weather_score:.0f}); typical high {_f(high)}°F, low {_f(low)}°F."
        ]
        if scenery_hit:
            reasons.append(f"Has the scenery you picked: {_join(_labels(scenery_hit, SCENERY))}.")
        if wildlife_hit:
            reasons.append(f"NPS lists {_join(_labels(wildlife_hit, WILDLIFE)).lower()} here.")
        if miles is not None:
            reasons.append(f"About {miles:,.0f} miles from {prefs.origin} in a straight line.")
        if code in TRAIL_GUIDE_PARKS:
            reasons.append("ParkMatch trail guide available for this park.")

        warnings = []
        if weather_label in ("Poor", "Fair"):
            warnings.append(f"{month_name} weather is only {weather_label.lower()} for {activity.value}.")
        if code in NO_ROAD_ACCESS:
            warnings.append(NO_ROAD_ACCESS[code])
        elif code in ISLAND_ACCESS:
            warnings.append(ISLAND_ACCESS[code])
        open_now = campgrounds_open(features, prefs.month)
        if activity is Activity.camping and open_now < features.campground_count:
            warnings.append(f"{open_now} of {features.campground_count} campgrounds are usually open in {month_name}.")

        results.append({
            "park_code": code,
            "park_name": park.park_name,
            "state": park.state,
            "latitude": park.latitude,
            "longitude": park.longitude,
            "score": round(score, 1),
            "parts": {k: round(v, 1) for k, v in parts.items()},
            "reasons": reasons,
            "warnings": warnings,
            "weather": {
                "month": prefs.month,
                "score": round(weather_score, 1),
                "label": weather_label,
                "temp_max_c": round(high, 1),
                "temp_min_c": round(low, 1),
                "wet_probability": round(float(month["wet"]), 3),
                "snow_probability": round(float(month["snow"]), 3),
            },
            "distance_miles": round(miles) if miles is not None else None,
            "access": "no_road" if code in NO_ROAD_ACCESS else "island" if code in ISLAND_ACCESS else "road",
            "scenery": _labels(scenery_all, SCENERY),
            "scenery_matched": scenery_hit,
            "wildlife": _labels(wildlife_all, WILDLIFE),
            "wildlife_matched": wildlife_hit,
            "amenities": [label for key, (label, test) in AMENITIES.items()
                          if key != "visitor_center" or features.visitor_center_count is not None
                          if test(features, prefs.month)],
            "campgrounds_open": open_now,
            "vehicle_fee_usd": features.vehicle_fee_usd,
            "nps_url": features.nps_url,
            "photo": _photo(features),
            "trail_guide": code in TRAIL_GUIDE_PARKS,
        })

    results.sort(key=lambda r: (-r["score"], r["park_name"]))
    poor_hidden = sum(1 for e in excluded.values() if " weather is poor " in e["reason"])
    return {
        "month": prefs.month,
        "activity": activity.value,
        "weights": weights,
        "considered": len(rows),
        "matched": len(results),
        "results": results[: prefs.limit],
        "excluded": dict(sorted(excluded.items(), key=lambda kv: kv[1]["park_name"])),
        "poor_weather_hidden": poor_hidden,
        "nearest_beyond_limit": nearest_beyond,
        "notes": options()["notes"],
    }
