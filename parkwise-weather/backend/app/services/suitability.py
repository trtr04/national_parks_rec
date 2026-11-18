"""
Weather suitability score (0–100) for an activity on one day.

Four components, each 0–100, combined with activity-specific weights:

    temperature    100 inside the activity's comfortable band for the daytime high,
                   minus 6 points per °C outside it. Camping also loses 8 points per °C
                   the night drops below 5 °C.
    precipitation  100 x (1 - chance of a wet day)
    wind           100 up to 20 km/h, falling to 0 at 60 km/h
    snow           100 x (1 - chance of a snow day)

Extreme heat (a high of 38 °C or more) caps hiking and camping at 30, because the
average of the other components shouldn't hide a safety problem.

Labels: 80+ Excellent, 65+ Good, 45+ Fair, otherwise Poor.
These are judgement calls, documented here so they can be argued with and tuned.
"""

from app.models.schemas import Activity

# Comfortable daytime high (°C) per activity.
COMFORT_BAND_C = {
    Activity.hiking: (12.0, 24.0),
    Activity.camping: (15.0, 27.0),
    Activity.sightseeing: (10.0, 28.0),
    Activity.wildlife: (5.0, 22.0),   # animals are most active in cooler weather
}

WEIGHTS = {
    Activity.hiking: {"temperature": 0.40, "precipitation": 0.35, "wind": 0.15, "snow": 0.10},
    Activity.camping: {"temperature": 0.40, "precipitation": 0.35, "wind": 0.15, "snow": 0.10},
    Activity.sightseeing: {"temperature": 0.30, "precipitation": 0.45, "wind": 0.15, "snow": 0.10},
    Activity.wildlife: {"temperature": 0.25, "precipitation": 0.40, "wind": 0.25, "snow": 0.10},
}

POINTS_PER_DEGREE = 6.0
CAMPING_COLD_NIGHT_C = 5.0
CAMPING_POINTS_PER_COLD_DEGREE = 8.0
CALM_WIND_KMH, MAX_WIND_KMH = 20.0, 60.0
HEAT_DANGER_C = 38.0
HEAT_CAP = 30.0

LABELS = ((80, "Excellent"), (65, "Good"), (45, "Fair"), (0, "Poor"))


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _f(celsius: float) -> str:
    return f"{celsius * 9 / 5 + 32:.0f}"


def label_for(score: float) -> str:
    return next(label for threshold, label in LABELS if score >= threshold)


def score_day(
    activity: Activity | str,
    temp_max_c: float,
    temp_min_c: float,
    wet_probability: float,
    wind_max_kmh: float | None,
    snow_probability: float,
) -> dict:
    """Return {"score", "label", "components", "weights", "notes"}."""
    activity = Activity(activity)
    low, high = COMFORT_BAND_C[activity]
    outside = max(0.0, low - temp_max_c, temp_max_c - high)
    temperature = 100.0 - POINTS_PER_DEGREE * outside
    if activity is Activity.camping:
        temperature -= CAMPING_POINTS_PER_COLD_DEGREE * max(0.0, CAMPING_COLD_NIGHT_C - temp_min_c)

    if wind_max_kmh is None:
        wind = 100.0
    else:
        wind = 100.0 * (MAX_WIND_KMH - wind_max_kmh) / (MAX_WIND_KMH - CALM_WIND_KMH)

    components = {
        "temperature": round(_clamp(temperature), 1),
        "precipitation": round(_clamp(100.0 * (1.0 - wet_probability)), 1),
        "wind": round(_clamp(wind), 1),
        "snow": round(_clamp(100.0 * (1.0 - snow_probability)), 1),
    }
    weights = WEIGHTS[activity]
    score = sum(components[k] * w for k, w in weights.items())

    notes = []
    if temp_max_c >= HEAT_DANGER_C and activity in (Activity.hiking, Activity.camping):
        score = min(score, HEAT_CAP)
        notes.append(f"Dangerous heat: highs around {temp_max_c:.0f} °C ({_f(temp_max_c)} °F).")
    if temp_max_c < low:
        notes.append(f"Colder than ideal for {activity.value} "
                     f"({low:.0f}–{high:.0f} °C / {_f(low)}–{_f(high)} °F is comfortable).")
    elif temp_max_c > high:
        notes.append(f"Warmer than ideal for {activity.value} "
                     f"({low:.0f}–{high:.0f} °C / {_f(low)}–{_f(high)} °F is comfortable).")
    if snow_probability >= 0.3:
        notes.append("Snow is likely.")

    score = round(_clamp(score), 1)
    return {
        "score": score,
        "label": label_for(score),
        "components": components,
        "weights": weights,
        "notes": notes,
    }
