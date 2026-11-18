"""
Weather data access and prediction.

    get_history()      reads weather_history
    get_seasonal()     monthly climate summary computed in SQL
    predict_weather()  forecast (next 16 days) or climate estimate (later), plus suitability
    compare_parks()    predict_weather() for several parks, ranked by suitability
    best_time()        month-by-month climate outlook and suitability for one park
"""

import datetime as dt
import logging

import pandas as pd
from sqlalchemy import case, extract, func, select
from sqlalchemy.orm import Session

from app.database.models import Park, WeatherHistory, WeatherPrediction
from app.models.schemas import Activity
from app.services import forecast_client, model_store
from app.services.climate_models import SNOW_DAY_THRESHOLD_CM, add_features
from app.services.errors import InvalidRequestError, ModelNotReadyError
from app.services.park_service import get_park
from app.services.suitability import label_for, score_day

logger = logging.getLogger("parkwise.weather")

# A "wet day" is one with >= 1.0 mm of precipitation — the usual climatology
# convention, which ignores trace amounts like dew or drizzle.
WET_DAY_THRESHOLD_MM = 1.0

# Guardrail so one request can't pull 10+ years of daily rows at once.
MAX_HISTORY_DAYS = 3 * 366

# Open-Meteo forecasts 16 days (today + 15). Later dates get a climate estimate.
FORECAST_HORIZON_DAYS = forecast_client.FORECAST_DAYS
# How far ahead the planner accepts travel dates.
MAX_PLANNING_DAYS = 3 * 365


def get_history(
    db: Session,
    park_code: str,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
) -> dict:
    """
    Daily observations for one park, oldest first.

    With no dates given, returns the most recent 365 days stored for that park.
    """
    park = get_park(db, park_code)

    if start_date and end_date and start_date > end_date:
        raise InvalidRequestError("start_date must be on or before end_date.")

    if end_date is None:
        end_date = db.scalar(
            select(func.max(WeatherHistory.date)).where(WeatherHistory.park_code == park.park_code)
        )
    if end_date is not None and start_date is None:
        start_date = end_date - dt.timedelta(days=364)

    if start_date and end_date and (end_date - start_date).days > MAX_HISTORY_DAYS:
        raise InvalidRequestError(
            f"Date range is too long. Request at most {MAX_HISTORY_DAYS} days at a time."
        )

    rows: list[WeatherHistory] = []
    if end_date is not None:  # None means no history stored yet
        stmt = (
            select(WeatherHistory)
            .where(WeatherHistory.park_code == park.park_code)
            .where(WeatherHistory.date.between(start_date, end_date))
            .order_by(WeatherHistory.date)
        )
        rows = list(db.scalars(stmt))

    return {
        "park_code": park.park_code,
        "start_date": start_date,
        "end_date": end_date,
        "count": len(rows),
        "observations": rows,
    }


def get_seasonal(db: Session, park_code: str) -> dict:
    """
    Month-by-month climate summary for one park, aggregated in SQL.

    Equivalent SQL (PostgreSQL):
        SELECT EXTRACT(MONTH FROM date)            AS month,
               AVG(temp_max), AVG(temp_min), AVG(precipitation),
               AVG(CASE WHEN precipitation >= 1.0 THEN 1.0
                        WHEN precipitation IS NULL THEN NULL
                        ELSE 0.0 END)              AS wet_day_frequency,
               COUNT(*)                            AS days_observed
        FROM weather_history
        WHERE park_code = :park_code
        GROUP BY 1
        ORDER BY 1;
    """
    park = get_park(db, park_code)

    month = extract("month", WeatherHistory.date)
    wet_day = case(
        (WeatherHistory.precipitation.is_(None), None),
        (WeatherHistory.precipitation >= WET_DAY_THRESHOLD_MM, 1.0),
        else_=0.0,
    )
    stmt = (
        select(
            month.label("month"),
            func.avg(WeatherHistory.temp_max).label("avg_temp_max"),
            func.avg(WeatherHistory.temp_min).label("avg_temp_min"),
            func.avg(WeatherHistory.precipitation).label("avg_precipitation"),
            func.avg(wet_day).label("wet_day_frequency"),
            func.count().label("days_observed"),
        )
        .where(WeatherHistory.park_code == park.park_code)
        .group_by(month)
        .order_by(month)
    )

    def _round(value, digits=2):
        return None if value is None else round(float(value), digits)

    months = [
        {
            "month": int(row.month),
            "avg_temp_max": _round(row.avg_temp_max),
            "avg_temp_min": _round(row.avg_temp_min),
            "avg_precipitation": _round(row.avg_precipitation),
            "wet_day_frequency": _round(row.wet_day_frequency, 3),
            "days_observed": int(row.days_observed),
        }
        for row in db.execute(stmt)
    ]

    first_date, last_date = db.execute(
        select(func.min(WeatherHistory.date), func.max(WeatherHistory.date)).where(
            WeatherHistory.park_code == park.park_code
        )
    ).one()

    return {
        "park_code": park.park_code,
        "wet_day_threshold_mm": WET_DAY_THRESHOLD_MM,
        "first_date": first_date,
        "last_date": last_date,
        "months": months,
    }


def validate_travel_date(travel_date: dt.date, today: dt.date | None = None) -> None:
    """Travel dates must be today or later, and within the planning window."""
    today = today or dt.date.today()
    if travel_date < today:
        raise InvalidRequestError("Travel date is in the past. Pick today or a later date.")
    if (travel_date - today).days > MAX_PLANNING_DAYS:
        raise InvalidRequestError(
            f"Travel date is too far ahead. Pick a date within {MAX_PLANNING_DAYS} days."
        )


# Typical forecast error grows with lead time. These approximate ±ranges (°C) are
# shown with forecasts; they are a rule of thumb, not a calibrated interval.
FORECAST_RANGE_BASE_C = 1.5
FORECAST_RANGE_PER_DAY_C = 0.2

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]


def _park_info(park: Park) -> dict:
    return {
        "park_code": park.park_code,
        "park_name": park.park_name,
        "state": park.state,
        "latitude": park.latitude,
        "longitude": park.longitude,
        "weather_location_note": park.weather_location_note,
    }


def _part_of_month(day: dt.date) -> str:
    part = "early" if day.day <= 10 else "mid" if day.day <= 20 else "late"
    return f"{part} {MONTH_NAMES[day.month - 1]}"


def _one_in(probability: float) -> str:
    """0.17 -> 'about 1 day in 6'."""
    if probability < 0.05:
        return "rarely"
    if probability > 0.9:
        return "almost every day"
    return f"about 1 day in {round(1 / probability)}"


def _climate_estimate(park: Park, travel_date: dt.date) -> dict:
    bundle = model_store.get_bundle()
    if park.park_code not in bundle["parks"]:
        raise ModelNotReadyError(
            f"The climate model has no weather history for '{park.park_code}' yet. "
            "Load its history and retrain the model."
        )

    lat, lon = bundle["parks"][park.park_code]
    frame = add_features(pd.DataFrame(
        {"park_code": [park.park_code], "date": [travel_date], "latitude": [lat], "longitude": [lon]}
    ))
    predicted = bundle["model"].predict(frame).iloc[0]
    temp_max, temp_min = float(predicted["temp_max"]), float(predicted["temp_min"])
    temp_min = min(temp_min, temp_max)  # the two are modelled separately
    wet = float(min(1.0, max(0.0, predicted["wet"])))

    climatology = bundle["climatology"]
    wind = float(climatology.lookup(frame["park_code"], frame["doy"], "wind_speed_max")[0])
    snow = float(climatology.lookup(frame["park_code"], frame["doy"], "snow_day")[0])

    month = travel_date.month - 1
    intervals = bundle["intervals"][park.park_code]
    lo_q, hi_q = bundle["interval_quantiles"]
    coverage = round((hi_q - lo_q) * 100)
    first_year, last_year = bundle["history_range"][0][:4], bundle["history_range"][1][:4]

    return {
        "prediction_type": "climate_estimate",
        "model_name": bundle["model_name"],
        "source": f"ParkWise climate model: {bundle['model_label']} (Open-Meteo history {first_year}–{last_year})",
        "temp_max": temp_max,
        "temp_min": temp_min,
        "max_range": [temp_max + intervals["temp_max"][month][0], temp_max + intervals["temp_max"][month][1]],
        "min_range": [temp_min + intervals["temp_min"][month][0], temp_min + intervals["temp_min"][month][1]],
        "range_note": f"{coverage}% range, set from this model's past errors at this park in this month.",
        "wet": wet,
        "precipitation_kind": "historical_frequency" if bundle["model_name"] == "seasonal_average"
                              else "climate_model_probability",
        "expected_precipitation_mm": None,
        "snow": snow,
        "wind": wind,
        "summary_lead": f"Typical for {_part_of_month(travel_date)} at {park.park_name} ({first_year}–{last_year})",
        "uncertainty": (
            "This is not a forecast. It describes what this time of year has usually been like, "
            "and the actual day can be quite different. Check the forecast again within 16 days of your trip."
        ),
    }


def _forecast(park: Park, travel_date: dt.date, days_ahead: int) -> dict:
    f = forecast_client.get_daily_forecast(park.latitude, park.longitude, travel_date)
    half_width = FORECAST_RANGE_BASE_C + FORECAST_RANGE_PER_DAY_C * days_ahead
    precipitation = f["precipitation"] or 0.0
    if f["precipitation_probability"] is not None:
        wet, kind = f["precipitation_probability"], "forecast_probability"
    else:  # some forecast models don't give a probability; fall back on the amount
        wet, kind = (0.6 if precipitation >= 1.0 else 0.1), "forecast_amount"
    snow = wet if (f["snowfall"] or 0.0) >= SNOW_DAY_THRESHOLD_CM else 0.0

    return {
        "prediction_type": "forecast",
        "model_name": "open_meteo_forecast",
        "source": "Open-Meteo Forecast API",
        "temp_max": f["temp_max"],
        "temp_min": f["temp_min"],
        "max_range": [f["temp_max"] - half_width, f["temp_max"] + half_width],
        "min_range": [f["temp_min"] - half_width, f["temp_min"] + half_width],
        "range_note": f"Approximate: forecasts {days_ahead} days out are typically within ±{half_width:.1f} °C.",
        "wet": wet,
        "precipitation_kind": kind,
        "expected_precipitation_mm": round(precipitation, 1),
        "snow": snow,
        "wind": f["wind_speed_max"],
        "summary_lead": "Forecast" if days_ahead else "Forecast for today",
        "uncertainty": "Forecasts are most reliable for the next few days and less so toward two weeks out.",
    }


def _log_prediction(db: Session, park_code: str, travel_date: dt.date, activity: Activity, r: dict, score: float):
    """Record every served prediction in weather_predictions. A logging failure never fails the request."""
    try:
        db.add(WeatherPrediction(
            park_code=park_code,
            target_date=travel_date,
            prediction_type=r["prediction_type"],
            model_name=r["model_name"],
            activity=activity.value,
            predicted_temp_max=r["temp_max"],
            predicted_temp_min=r["temp_min"],
            precipitation_probability=r["wet"],
            weather_suitability_score=score,
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not log prediction for %s %s", park_code, travel_date)


def predict_weather(
    db: Session,
    park_code: str,
    travel_date: dt.date,
    activity: Activity | str = Activity.hiking,
    today: dt.date | None = None,
) -> dict:
    """
    Weather outlook for one park on one travel date — the function teammates import.

    Dates from today to today + 15 get the live Open-Meteo forecast. Later dates (or any
    date when the forecast can't be reached) get a climate estimate from the trained model.

    Returns a JSON-compatible dict:
        {
          "park": {park_code, park_name, state, latitude, longitude, weather_location_note},
          "travel_date": "2027-04-15", "days_ahead": 167, "activity": "hiking",
          "prediction_type": "forecast" | "climate_estimate",
          "model_name": "open_meteo_forecast" | "<selected climate model>",
          "source": "...",
          "units": {...},
          "temperature": {"max_c", "min_c", "max_range_c": [lo, hi], "min_range_c": [lo, hi], "range_note"},
          "precipitation": {"probability", "kind", "wet_day_threshold_mm", "expected_mm"},
          "snow": {"probability"},
          "wind": {"max_kmh"},
          "suitability": {"score", "label", "components", "weights", "notes"},
          "summary": "short plain-language explanation",
          "uncertainty": "...",
          "notes": [...],
          "generated_at": "ISO-8601 timestamp"
        }
    """
    park = get_park(db, park_code)
    today = today or dt.date.today()
    validate_travel_date(travel_date, today)
    activity = Activity(activity)
    days_ahead = (travel_date - today).days

    notes: list[str] = []
    result = None
    if days_ahead < FORECAST_HORIZON_DAYS:
        try:
            result = _forecast(park, travel_date, days_ahead)
        except forecast_client.ForecastUnavailableError as exc:
            logger.warning("Forecast unavailable for %s %s: %s", park.park_code, travel_date, exc)
            notes.append("The live forecast couldn't be reached, so this is a climate estimate instead.")
    if result is None:
        result = _climate_estimate(park, travel_date)

    suitability = score_day(activity, result["temp_max"], result["temp_min"], result["wet"],
                            result["wind"], result["snow"])
    _log_prediction(db, park.park_code, travel_date, activity, result, suitability["score"])

    r1 = lambda v: None if v is None else round(float(v), 1)  # noqa: E731
    summary = (
        f"{result['summary_lead']}: highs around {result['temp_max']:.0f} °C "
        f"({result['max_range'][0]:.0f} to {result['max_range'][1]:.0f}), lows around {result['temp_min']:.0f} °C. "
        + (f"Chance of precipitation {result['wet']:.0%}. " if result["prediction_type"] == "forecast"
           else f"Rain or snow on {_one_in(result['wet'])}. ")
        + f"{suitability['label']} for {activity.value} ({suitability['score']:.0f}/100)."
    )

    return {
        "park": _park_info(park),
        "travel_date": travel_date.isoformat(),
        "days_ahead": days_ahead,
        "activity": activity.value,
        "prediction_type": result["prediction_type"],
        "model_name": result["model_name"],
        "source": result["source"],
        "units": {"temperature": "celsius", "precipitation": "mm", "wind_speed": "km/h"},
        "temperature": {
            "max_c": r1(result["temp_max"]),
            "min_c": r1(result["temp_min"]),
            "max_range_c": [r1(v) for v in result["max_range"]],
            "min_range_c": [r1(v) for v in result["min_range"]],
            "range_note": result["range_note"],
        },
        "precipitation": {
            "probability": round(result["wet"], 3),
            "kind": result["precipitation_kind"],
            "wet_day_threshold_mm": WET_DAY_THRESHOLD_MM,
            "expected_mm": result["expected_precipitation_mm"],
        },
        "snow": {"probability": round(result["snow"], 3)},
        "wind": {"max_kmh": r1(result["wind"])},
        "suitability": suitability,
        "summary": summary,
        "uncertainty": result["uncertainty"],
        "notes": notes + suitability["notes"],
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }


def best_time(db: Session, park_code: str) -> dict:
    """
    Month-by-month climate outlook for one park, scored for every activity.

    Each day of a reference year gets a climate estimate and a suitability score; a
    month's score is the mean of its days. Year-to-year spread comes from the stored
    history: the coolest and warmest year's average high for that month, and the
    driest and wettest year's share of wet days.
    """
    park = get_park(db, park_code)
    bundle = model_store.get_bundle()
    if park.park_code not in bundle["parks"]:
        raise ModelNotReadyError(
            f"The climate model has no weather history for '{park.park_code}' yet. "
            "Load its history and retrain the model."
        )

    year = dt.date.today().year + 1
    days = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    lat, lon = bundle["parks"][park.park_code]
    frame = add_features(pd.DataFrame(
        {"park_code": park.park_code, "date": days.date, "latitude": lat, "longitude": lon}
    ))
    predicted = bundle["model"].predict(frame)
    climatology = bundle["climatology"]
    daily = pd.DataFrame({
        "month": days.month,
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

    # Year-to-year spread from history (one row per year and month).
    hist_year, hist_month = extract("year", WeatherHistory.date), extract("month", WeatherHistory.date)
    wet_day = case(
        (WeatherHistory.precipitation.is_(None), None),
        (WeatherHistory.precipitation >= WET_DAY_THRESHOLD_MM, 1.0),
        else_=0.0,
    )
    yearly = pd.DataFrame(db.execute(
        select(hist_year.label("year"), hist_month.label("month"),
               func.avg(WeatherHistory.temp_max).label("avg_high"), func.avg(wet_day).label("wet_share"))
        .where(WeatherHistory.park_code == park.park_code)
        .group_by(hist_year, hist_month)
    ).all(), columns=["year", "month", "avg_high", "wet_share"])

    r1 = lambda v: None if v is None or pd.isna(v) else round(float(v), 1)  # noqa: E731
    months = []
    for month, group in daily.groupby("month"):
        spread = yearly[yearly["month"] == month]
        scores = {a.value: r1(group[a.value].mean()) for a in Activity}
        months.append({
            "month": int(month),
            "temp_max_c": r1(group["temp_max"].mean()),
            "temp_min_c": r1(group["temp_min"].mean()),
            "wet_probability": round(float(group["wet"].mean()), 3),
            "snow_probability": round(float(group["snow"].mean()), 3),
            "wind_max_kmh": r1(group["wind"].mean()),
            "scores": scores,
            "labels": {a: label_for(s) for a, s in scores.items()},
            "year_to_year": {
                "years": int(spread["year"].nunique()),
                "avg_high_c": [r1(spread["avg_high"].min()), r1(spread["avg_high"].max())],
                "wet_share": [round(float(spread["wet_share"].min()), 3), round(float(spread["wet_share"].max()), 3)]
                if len(spread) else [None, None],
            },
        })

    best = {a.value: [m["month"] for m in sorted(months, key=lambda m: -m["scores"][a.value])[:3]]
            for a in Activity}
    first_year, last_year = bundle["history_range"][0][:4], bundle["history_range"][1][:4]
    return {
        "park": _park_info(park),
        "model_name": bundle["model_name"],
        "source": f"ParkWise climate model: {bundle['model_label']} (Open-Meteo history {first_year}–{last_year})",
        "units": {"temperature": "celsius", "wind_speed": "km/h"},
        "wet_day_threshold_mm": WET_DAY_THRESHOLD_MM,
        "best_months": best,
        "months": months,
    }


def compare_parks(
    db: Session,
    park_codes: list[str],
    travel_date: dt.date,
    activity: Activity | str = Activity.hiking,
    today: dt.date | None = None,
) -> dict:
    """predict_weather() for each park, best suitability first."""
    if len({code.strip().lower() for code in park_codes}) != len(park_codes):
        raise InvalidRequestError("Each park can only appear once in a comparison.")
    results = [predict_weather(db, code, travel_date, activity, today) for code in park_codes]
    results.sort(key=lambda r: r["suitability"]["score"], reverse=True)
    for rank, r in enumerate(results, start=1):
        r["rank"] = rank
    return {
        "travel_date": travel_date.isoformat(),
        "activity": Activity(activity).value,
        "best_park_code": results[0]["park"]["park_code"],
        "results": results,
    }
