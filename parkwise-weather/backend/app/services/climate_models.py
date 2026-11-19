"""
Climate-estimate models: what a given day of the year is typically like at a park.

These answer "what should I expect on 15 April 2027 at Zion?" when the date is too far
away for a real forecast. None of them sees recent weather, because months ahead
nobody can; they learn the seasonal cycle (and, for the regression, a slow trend).

Three models, all with the same fit(frame) / predict(frame) interface:

    seasonal_average     Baseline. For each park and day of year, the mean of the
                         training years within ±7 days. Wet-day probability is the
                         share of those days with >= 1 mm of precipitation.
    seasonal_regression  One linear model per park on three yearly harmonics
                         (sin/cos of the day of year), plus one linear year trend
                         shared by all parks (ten years is too short to estimate a
                         trustworthy trend for each park on its own); logistic
                         regression on the harmonics for wet days.
    random_forest        One model across all parks: location, season harmonics,
                         the park's own climatology for that day, and the year.

Targets: daily temp_max (°C), daily temp_min (°C), and P(wet day).
Evaluation and model selection live in scripts/train_models.py.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression

WET_DAY_THRESHOLD_MM = 1.0   # same convention as the seasonal summary endpoint
SNOW_DAY_THRESHOLD_CM = 1.0
WINDOW_DAYS = 7               # climatology averages ±7 days around the date
TREND_ORIGIN_YEAR = 2020      # centres the year feature so coefficients stay readable

TARGETS = ("temp_max", "temp_min", "wet")


# ---------- features ----------

def day_of_year(dates: pd.Series) -> np.ndarray:
    return pd.to_datetime(dates).dt.day_of_year.to_numpy()


def add_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add day-of-year, year, seasonal harmonics and the wet/snow-day indicators."""
    out = frame.copy()
    dates = pd.to_datetime(out["date"])
    out["doy"] = dates.dt.day_of_year
    out["year"] = dates.dt.year
    angle = 2 * math.pi * (out["doy"] - 1) / 365.25
    for k in (1, 2, 3):
        out[f"sin{k}"] = np.sin(k * angle)
        out[f"cos{k}"] = np.cos(k * angle)
    out["trend"] = out["year"] - TREND_ORIGIN_YEAR
    if "precipitation" in out:
        out["wet"] = np.where(out["precipitation"].isna(), np.nan,
                              (out["precipitation"] >= WET_DAY_THRESHOLD_MM).astype(float))
    if "snowfall" in out:
        out["snow_day"] = np.where(out["snowfall"].isna(), np.nan,
                                   (out["snowfall"] >= SNOW_DAY_THRESHOLD_CM).astype(float))
    return out


HARMONICS = ["sin1", "cos1", "sin2", "cos2", "sin3", "cos3"]


# ---------- climatology (the baseline, and an input to the forest) ----------

class Climatology:
    """
    Per park, per day of year (1–366): circular ±WINDOW_DAYS mean of each variable.

    Day 366 only exists in leap years, but the window borrows from its neighbours,
    so every day has a value.
    """

    VARIABLES = ("temp_max", "temp_min", "wet", "snow_day", "wind_speed_max")

    def __init__(self, window: int = WINDOW_DAYS):
        self.window = window
        self.tables: dict[str, dict[str, np.ndarray]] = {}

    def fit(self, frame: pd.DataFrame) -> Climatology:
        kernel = np.ones(2 * self.window + 1)
        for park_code, group in frame.groupby("park_code"):
            idx = group["doy"].to_numpy() - 1
            park_table = {}
            for var in self.VARIABLES:
                values = group[var].to_numpy(dtype=float)
                known = ~np.isnan(values)
                sums = np.bincount(idx[known], weights=values[known], minlength=366)
                counts = np.bincount(idx[known], minlength=366).astype(float)
                # Circular convolution: pad both ends so late December borrows from early January.
                pad = self.window
                s = np.convolve(np.concatenate([sums[-pad:], sums, sums[:pad]]), kernel, "valid")
                c = np.convolve(np.concatenate([counts[-pad:], counts, counts[:pad]]), kernel, "valid")
                with np.errstate(invalid="ignore", divide="ignore"):
                    park_table[var] = np.where(c > 0, s / c, np.nan)
            self.tables[park_code] = park_table
        return self

    def lookup(self, park_codes: pd.Series, doy: pd.Series, var: str) -> np.ndarray:
        out = np.full(len(park_codes), np.nan)
        codes = park_codes.to_numpy()
        days = doy.to_numpy() - 1
        for code in np.unique(codes):
            mask = codes == code
            if code in self.tables:
                out[mask] = self.tables[code][var][days[mask]]
        return out

    @property
    def park_codes(self) -> list[str]:
        return sorted(self.tables)


# ---------- the three models ----------

class SeasonalAverageModel:
    name = "seasonal_average"
    label = "Seasonal average (baseline)"

    def fit(self, frame: pd.DataFrame) -> SeasonalAverageModel:
        self.climatology = Climatology().fit(frame)
        return self

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        c = self.climatology
        return pd.DataFrame(
            {
                "temp_max": c.lookup(frame["park_code"], frame["doy"], "temp_max"),
                "temp_min": c.lookup(frame["park_code"], frame["doy"], "temp_min"),
                "wet": c.lookup(frame["park_code"], frame["doy"], "wet"),
            },
            index=frame.index,
        )


class SeasonalRegressionModel:
    name = "seasonal_regression"
    label = "Seasonal regression with trend"
    FEATURES = HARMONICS

    def fit(self, frame: pd.DataFrame) -> SeasonalRegressionModel:
        """
        Two stages. 1) Per park, temperature on the harmonics. 2) One shared trend:
        every park's leftover error regressed on (year - that park's mean year),
        so the trend can't be confused with differences between parks.
        """
        self.models: dict[str, dict[str, object]] = {}
        self.mean_trend: dict[str, float] = {}
        residuals = {"temp_max": [], "temp_min": []}
        centred_trends = []
        for park_code, group in frame.groupby("park_code"):
            X = group[self.FEATURES].to_numpy()
            self.mean_trend[park_code] = float(group["trend"].mean())
            centred_trends.append(group["trend"].to_numpy() - self.mean_trend[park_code])
            park_models: dict[str, object] = {}
            for target in ("temp_max", "temp_min"):
                y = group[target].to_numpy()
                known = ~np.isnan(y)
                park_models[target] = LinearRegression().fit(X[known], y[known])
                residuals[target].append(y - park_models[target].predict(X))
            known = group["wet"].notna().to_numpy()
            y = group["wet"].to_numpy()[known]
            if len(np.unique(y)) < 2:
                # Never (or always) wet in training: a constant, kept off exactly 0 or 1.
                park_models["wet"] = float(np.clip(y.mean() if len(y) else 0.0, 0.002, 0.998))
            else:
                park_models["wet"] = LogisticRegression(C=1.0, max_iter=1000).fit(X[known], y)
            self.models[park_code] = park_models

        t = np.concatenate(centred_trends)
        self.trend_per_year: dict[str, float] = {}
        for target in ("temp_max", "temp_min"):
            r = np.concatenate(residuals[target])
            known = ~np.isnan(r)
            self.trend_per_year[target] = float(np.dot(t[known], r[known]) / np.dot(t[known], t[known]))
        return self

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(np.nan, index=frame.index, columns=list(TARGETS))
        for park_code, group in frame.groupby("park_code"):
            if park_code not in self.models:
                continue
            m = self.models[park_code]
            X = group[self.FEATURES].to_numpy()
            years_from_mean = group["trend"].to_numpy() - self.mean_trend[park_code]
            for target in ("temp_max", "temp_min"):
                out.loc[group.index, target] = m[target].predict(X) + self.trend_per_year[target] * years_from_mean
            wet = m["wet"]
            out.loc[group.index, "wet"] = wet if isinstance(wet, float) else wet.predict_proba(X)[:, 1]
        return out


class RandomForestModel:
    name = "random_forest"
    label = "Random forest"
    FEATURES = ["latitude", "longitude", "sin1", "cos1", "sin2", "cos2",
                "clim_temp_max", "clim_temp_min", "clim_wet", "year"]

    def __init__(self, n_estimators: int = 80, min_samples_leaf: int = 50, random_state: int = 42):
        self.params = dict(
            n_estimators=n_estimators,
            min_samples_leaf=min_samples_leaf,
            max_features=0.5,
            max_samples=0.5,   # each tree sees half the rows: faster, and smaller files
            n_jobs=-1,
            random_state=random_state,
        )

    def _features(self, frame: pd.DataFrame) -> pd.DataFrame:
        X = frame.copy()
        for var in ("temp_max", "temp_min", "wet"):
            X[f"clim_{var}"] = self.climatology.lookup(frame["park_code"], frame["doy"], var)
        return X[self.FEATURES]

    def fit(self, frame: pd.DataFrame) -> RandomForestModel:
        self.climatology = Climatology().fit(frame)
        X = self._features(frame)
        self.models = {}
        for target in ("temp_max", "temp_min"):
            known = frame[target].notna().to_numpy()
            self.models[target] = RandomForestRegressor(**self.params).fit(X[known], frame[target][known])
        known = frame["wet"].notna().to_numpy()
        self.models["wet"] = RandomForestClassifier(**self.params).fit(X[known], frame["wet"][known].astype(int))
        return self

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        X = self._features(frame)
        wet_model = self.models["wet"]
        wet_col = list(wet_model.classes_).index(1) if 1 in wet_model.classes_ else None
        return pd.DataFrame(
            {
                "temp_max": self.models["temp_max"].predict(X),
                "temp_min": self.models["temp_min"].predict(X),
                "wet": wet_model.predict_proba(X)[:, wet_col] if wet_col is not None else 0.0,
            },
            index=frame.index,
        )


MODEL_CLASSES = {cls.name: cls for cls in (SeasonalAverageModel, SeasonalRegressionModel, RandomForestModel)}


# ---------- metrics ----------

def evaluate(actual: pd.DataFrame, predicted: pd.DataFrame) -> dict[str, float]:
    """MAE and RMSE for both temperatures, Brier score for the wet-day probability."""
    metrics: dict[str, float] = {}
    for target in ("temp_max", "temp_min"):
        err = (predicted[target] - actual[target]).dropna()
        metrics[f"{target}_mae"] = float(err.abs().mean())
        metrics[f"{target}_rmse"] = float(np.sqrt((err**2).mean()))
    pair = pd.DataFrame({"p": predicted["wet"], "y": actual["wet"]}).dropna()
    metrics["wet_brier"] = float(((pair["p"] - pair["y"]) ** 2).mean())
    metrics["rows"] = int(len(actual))
    return metrics
