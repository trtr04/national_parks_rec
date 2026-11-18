"""
Phase 3: train, evaluate and select the climate-estimate model.

Usage, from the backend/ folder (after the weather ETL):
    python -m scripts.train_models

Chronological split (never shuffled, so no future weather leaks into training):
    train       2015–2021
    validation  2022–2023   used to choose the model
    test        2024–2025   touched once, to report final accuracy

Steps
    1. Fit every model on train, score on validation.
    2. Choose the model with the best validation score, where the score adds up each
       metric relative to the baseline (temp_max MAE, temp_min MAE, wet-day Brier).
       A model must beat the baseline to replace it.
    3. Refit every model on train + validation and score it on test (reported for all
       models, so the comparison is honest).
    4. Ranges: per park and month, the 10th and 90th percentiles of the chosen model's
       errors give an 80% range. The errors come from leave-one-year-out fits on the
       train + validation years (each year predicted by a model that never saw it),
       which gives ~8x more errors per park-month than the validation years alone.
       Test coverage of that range is reported.
    5. Refit the chosen model on every year and save it for the API.

Writes
    trained_models/climate_model.joblib   the model the API serves (git-ignored)
    trained_models/metrics.json           all scores (small, safe to commit)
"""

import datetime as dt
import json
import logging
import sys
from dataclasses import dataclass

import joblib
import numpy as np
import pandas as pd
import sklearn
from sqlalchemy import select

from app.config import get_settings
from app.database.connection import SessionLocal
from app.database.models import Park, WeatherHistory
from app.services.climate_models import (
    MODEL_CLASSES,
    Climatology,
    SeasonalAverageModel,
    add_features,
    evaluate,
)

logger = logging.getLogger("parkwise.train")

BUNDLE_FILE = "climate_model.joblib"
METRICS_FILE = "metrics.json"
BUNDLE_VERSION = 1
INTERVAL_QUANTILES = (0.10, 0.90)


@dataclass(frozen=True)
class Split:
    train: tuple[int, int] = (2015, 2021)
    validation: tuple[int, int] = (2022, 2023)
    test: tuple[int, int] = (2024, 2025)

    def take(self, frame: pd.DataFrame, years: tuple[int, int]) -> pd.DataFrame:
        return frame[frame["year"].between(*years)]


def load_history(db) -> pd.DataFrame:
    stmt = select(
        WeatherHistory.park_code, WeatherHistory.date, WeatherHistory.temp_max, WeatherHistory.temp_min,
        WeatherHistory.precipitation, WeatherHistory.snowfall, WeatherHistory.wind_speed_max,
        Park.latitude, Park.longitude,
    ).join(Park, Park.park_code == WeatherHistory.park_code)
    return pd.DataFrame(db.execute(stmt).all())


def selection_score(metrics: dict, baseline: dict) -> float:
    """Sum of each metric divided by the baseline's. The baseline scores exactly 3.0; lower is better."""
    return (
        metrics["temp_max_mae"] / baseline["temp_max_mae"]
        + metrics["temp_min_mae"] / baseline["temp_min_mae"]
        + metrics["wet_brier"] / baseline["wet_brier"]
    )


def residual_quantiles(frame: pd.DataFrame, predicted: pd.DataFrame) -> dict:
    """{park: {target: array(12, 2)}}: per-month 10th/90th percentile of (actual - predicted)."""
    resid = pd.DataFrame({
        "park_code": frame["park_code"],
        "month": pd.to_datetime(frame["date"]).dt.month,
        "temp_max": frame["temp_max"] - predicted["temp_max"],
        "temp_min": frame["temp_min"] - predicted["temp_min"],
    })
    out: dict[str, dict[str, np.ndarray]] = {}
    for park_code, group in resid.groupby("park_code"):
        out[park_code] = {}
        for target in ("temp_max", "temp_min"):
            table = np.zeros((12, 2))
            overall = group[target].quantile(INTERVAL_QUANTILES).to_numpy()
            for month in range(1, 13):
                values = group.loc[group["month"] == month, target].dropna()
                table[month - 1] = values.quantile(INTERVAL_QUANTILES).to_numpy() if len(values) >= 20 else overall
            out[park_code][target] = table
    return out


def leave_one_year_out(frame: pd.DataFrame, model_cls) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Predict each year with a model fitted on all the other years. Returns (frame, predictions)."""
    predictions = []
    for year in sorted(frame["year"].unique()):
        held_out = frame[frame["year"] == year]
        model = model_cls().fit(frame[frame["year"] != year])
        predictions.append(model.predict(held_out))
    return frame, pd.concat(predictions).loc[frame.index]


def interval_coverage(frame: pd.DataFrame, predicted: pd.DataFrame, quantiles: dict) -> dict[str, float]:
    """Share of actual temperatures that fall inside the predicted 80% range."""
    months = pd.to_datetime(frame["date"]).dt.month.to_numpy() - 1
    coverage = {}
    for target in ("temp_max", "temp_min"):
        lo = np.full(len(frame), np.nan)
        hi = np.full(len(frame), np.nan)
        codes = frame["park_code"].to_numpy()
        for code in np.unique(codes):
            if code not in quantiles:
                continue
            mask = codes == code
            table = quantiles[code][target]
            lo[mask] = table[months[mask], 0]
            hi[mask] = table[months[mask], 1]
        actual = frame[target].to_numpy()
        pred = predicted[target].to_numpy()
        ok = ~np.isnan(actual) & ~np.isnan(lo)
        inside = (actual[ok] >= pred[ok] + lo[ok]) & (actual[ok] <= pred[ok] + hi[ok])
        coverage[target] = float(inside.mean()) if ok.any() else float("nan")
    return coverage


def train_and_evaluate(history: pd.DataFrame, split: Split = Split()) -> tuple[dict, dict]:
    """Everything except loading and saving. Returns (bundle, metrics)."""
    frame = add_features(history)
    train, val, test = split.take(frame, split.train), split.take(frame, split.validation), split.take(frame, split.test)
    for name, part in (("train", train), ("validation", val), ("test", test)):
        if part.empty:
            raise ValueError(f"No weather history in the {name} years. Load 2015–2025 first.")
    train_val = pd.concat([train, val])

    results: dict[str, dict] = {}
    val_predictions: dict[str, pd.DataFrame] = {}
    test_predictions: dict[str, pd.DataFrame] = {}
    for name, cls in MODEL_CLASSES.items():
        logger.info("Fitting %s on train, scoring on validation", name)
        model = cls().fit(train)
        val_predictions[name] = model.predict(val)
        logger.info("Refitting %s on train + validation, scoring on test", name)
        refit = cls().fit(train_val)
        test_predictions[name] = refit.predict(test)
        results[name] = {
            "label": cls.label,
            "validation": evaluate(val, val_predictions[name]),
            "test": evaluate(test, test_predictions[name]),
        }

    baseline_val = results[SeasonalAverageModel.name]["validation"]
    baseline_test = results[SeasonalAverageModel.name]["test"]
    for name, r in results.items():
        r["validation_score"] = round(selection_score(r["validation"], baseline_val), 4)
        r["test_brier_skill"] = round(1 - r["test"]["wet_brier"] / baseline_test["wet_brier"], 4)
    selected = min(results, key=lambda n: results[n]["validation_score"])
    logger.info("Selected %s (validation score %.4f; baseline = 3.0)", selected, results[selected]["validation_score"])

    # 80% ranges: calibrated on validation errors, checked on test.
    logger.info("Leave-one-year-out errors for the 80%% ranges")
    calibration = residual_quantiles(*leave_one_year_out(train_val, MODEL_CLASSES[selected]))
    coverage = interval_coverage(test, test_predictions[selected], calibration)
    # For serving, every year (test included) is held out once.
    serving_quantiles = residual_quantiles(*leave_one_year_out(frame, MODEL_CLASSES[selected]))

    per_park = []
    sel_test = test_predictions[selected]
    for park_code, group in test.groupby("park_code"):
        p = sel_test.loc[group.index]
        per_park.append({
            "park_code": park_code,
            "temp_max_mae": round(float((p["temp_max"] - group["temp_max"]).abs().mean()), 3),
            "temp_min_mae": round(float((p["temp_min"] - group["temp_min"]).abs().mean()), 3),
            "wet_brier": round(float(((p["wet"] - group["wet"]) ** 2).mean()), 4),
        })
    per_month = []
    test_month = pd.to_datetime(test["date"]).dt.month
    for month in range(1, 13):
        idx = test.index[test_month == month]
        if len(idx):
            per_month.append({
                "month": month,
                "temp_max_mae": round(float((sel_test.loc[idx, "temp_max"] - test.loc[idx, "temp_max"]).abs().mean()), 3),
                "wet_brier": round(float(((sel_test.loc[idx, "wet"] - test.loc[idx, "wet"]) ** 2).mean()), 4),
            })

    # Chart data for the Model insights page.
    by_month_all = {
        name: [round(float((pred.loc[test.index[test_month == m], "temp_max"]
                            - test.loc[test_month == m, "temp_max"]).abs().mean()), 3)
               for m in range(1, 13) if (test_month == m).any()]
        for name, pred in test_predictions.items()
    }
    errors = (sel_test["temp_max"] - test["temp_max"]).dropna()
    edges = np.arange(-15, 16)
    counts, _ = np.histogram(errors.clip(-14.999, 14.999), bins=edges)
    sample = test[["park_code", "date", "temp_max"]].assign(temp_max_pred=sel_test["temp_max"]).dropna()
    sample = sample.sample(n=min(500, len(sample)), random_state=42)

    logger.info("Refitting %s on every year for serving", selected)
    final_model = MODEL_CLASSES[selected]().fit(frame)
    parks = frame.groupby("park_code")[["latitude", "longitude"]].first()

    trained_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    bundle = {
        "version": BUNDLE_VERSION,
        "sklearn_version": sklearn.__version__,
        "trained_at": trained_at,
        "model_name": selected,
        "model_label": MODEL_CLASSES[selected].label,
        "model": final_model,
        "climatology": Climatology().fit(frame),   # typical wind and snow, shown alongside
        "intervals": serving_quantiles,
        "interval_quantiles": INTERVAL_QUANTILES,
        "parks": {code: (row.latitude, row.longitude) for code, row in parks.iterrows()},
        "history_range": [str(frame["date"].min()), str(frame["date"].max())],
    }

    def rounded(d: dict) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}

    metrics = {
        "trained_at": trained_at,
        "selected_model": selected,
        "selection_rule": "Lowest validation score: sum of temp_max MAE, temp_min MAE and wet-day Brier, "
                          "each divided by the baseline's. Baseline = 3.0, lower is better.",
        "split": {"train": list(split.train), "validation": list(split.validation), "test": list(split.test)},
        "rows": {"train": len(train), "validation": len(val), "test": len(test)},
        "parks": int(frame["park_code"].nunique()),
        "units": {"temp_mae": "°C", "temp_rmse": "°C", "wet_brier": "0 (perfect) to 1"},
        "wet_day_threshold_mm": 1.0,
        "models": {
            name: {
                "label": r["label"],
                "validation": rounded(r["validation"]),
                "test": rounded(r["test"]),
                "validation_score": r["validation_score"],
                "test_brier_skill_vs_baseline": r["test_brier_skill"],
            }
            for name, r in results.items()
        },
        "interval": {
            "nominal_coverage": INTERVAL_QUANTILES[1] - INTERVAL_QUANTILES[0],
            "test_coverage": {k: round(v, 4) for k, v in coverage.items()},
        },
        "selected_model_test_by_park": per_park,
        "selected_model_test_by_month": per_month,
        # Test-year temp_max MAE by month (Jan..Dec) for every model.
        "test_temp_max_mae_by_month": by_month_all,
        # Selected model's test-year temp_max errors (predicted - actual), in 1 °C bins.
        "selected_model_test_error_histogram": {
            "bin_start_c": edges[:-1].tolist(),
            "count": counts.tolist(),
            "within_3c": round(float((errors.abs() <= 3).mean()), 4),
        },
        # 500 random test days: predicted vs actual daily high.
        "selected_model_test_sample": [
            {"park_code": r.park_code, "date": str(r.date),
             "actual": round(float(r.temp_max), 1), "predicted": round(float(r.temp_max_pred), 1)}
            for r in sample.itertuples()
        ],
    }
    return bundle, metrics


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with SessionLocal() as db:
        history = load_history(db)
    if history.empty:
        logger.error("weather_history is empty. Run `python -m scripts.load_weather_history` first.")
        return 1
    logger.info("Loaded %d rows for %d parks", len(history), history["park_code"].nunique())

    bundle, metrics = train_and_evaluate(history)

    model_dir = get_settings().model_dir
    model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, model_dir / BUNDLE_FILE, compress=3)
    (model_dir / METRICS_FILE).write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print(f"\nSelected model: {metrics['selected_model']}\n")
    print(f"{'model':22} {'val score':>9} {'test Tmax MAE':>14} {'test Tmin MAE':>14} {'test Brier':>11}")
    for name, m in metrics["models"].items():
        t = m["test"]
        print(f"{name:22} {m['validation_score']:>9.3f} {t['temp_max_mae']:>14.2f} "
              f"{t['temp_min_mae']:>14.2f} {t['wet_brier']:>11.4f}")
    cov = metrics["interval"]["test_coverage"]
    print(f"\n80% range, test coverage: temp_max {cov['temp_max']:.1%}, temp_min {cov['temp_min']:.1%}")
    print(f"Saved {model_dir / BUNDLE_FILE} and {model_dir / METRICS_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
