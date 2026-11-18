"""
Synthetic daily weather for tests: a clean seasonal cycle plus noise, 2015–2025.

Only for exercising the training and prediction code paths. It is not real weather
and is never written to the real database.
"""

import numpy as np
import pandas as pd

# park_code, latitude, longitude, mean daily high (°C), wet-day chance
TEST_PARKS = [
    ("tstp", 37.0, -119.0, 12.0, 0.30),   # cooler, wetter
    ("tstv", 37.2, -113.0, 22.0, 0.08),   # warmer, drier
]


def synthetic_history(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-01", "2025-12-31")
    season = np.sin(2 * np.pi * (dates.day_of_year.to_numpy() - 110) / 365.25)  # peaks in late July
    frames = []
    for code, lat, lon, mean_high, wet_chance in TEST_PARKS:
        n = len(dates)
        temp_max = mean_high + 11 * season + rng.normal(0, 3, n)
        temp_min = temp_max - 13 + rng.normal(0, 2, n)
        wet = rng.random(n) < wet_chance * (1 - 0.6 * season)
        precipitation = np.where(wet, 1 + rng.exponential(6, n), rng.uniform(0, 0.9, n) * (rng.random(n) < 0.2))
        snowfall = np.where(wet & (temp_max < 2), precipitation * 0.7, 0.0)
        frames.append(pd.DataFrame({
            "park_code": code, "date": dates.date, "temp_max": temp_max, "temp_min": temp_min,
            "precipitation": precipitation, "snowfall": snowfall,
            "wind_speed_max": 12 + 6 * rng.random(n), "latitude": lat, "longitude": lon,
        }))
    return pd.concat(frames, ignore_index=True)
