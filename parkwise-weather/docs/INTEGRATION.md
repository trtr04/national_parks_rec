# Integrating ParkWise Weather

How the rest of the ParkWise travel planner can use the weather service. There are two ways in:

1. **Over HTTP** (any language, any frontend): call the deployed API. This is the normal route.
2. **In Python** (a teammate's backend in the same codebase): import `predict_weather()` directly.

Base URL: the Render service, e.g. `https://parkwise-weather-api.onrender.com`. Locally:
`http://127.0.0.1:8000`. Interactive docs with "Try it out" are always at `/docs`, and the
machine-readable OpenAPI schema at `/openapi.json` (use it to generate a typed client).

---

## Core ideas (read these first)

- **Two kinds of answer.** Travel dates from today to today + 15 get the live Open-Meteo
  **forecast**. Later dates (up to 3 years ahead) get a **climate estimate**: what that time of year
  has typically been like, from 2015–2025 history. Every response says which in `prediction_type`.
  Show it to users. A climate estimate is not a forecast.
- **Units are metric** in every response: °C, mm, km/h (also listed in each response's `units`).
  The ParkWise site converts to °F, inches and mph for display; `frontend/src/services/units.js`
  has the conversions.
- **Dates** are calendar dates, `YYYY-MM-DD`, with no time zone. Past dates are rejected.
- **Parks** are identified by the 4-letter NPS code (`yose`, `zion`, `grca`…). `GET /api/parks` lists
  all 63 National Parks.
- **Activities**: `hiking` (default), `camping`, `sightseeing`, `wildlife`. Each gets its own
  0–100 suitability score.

## Endpoints

| Method | Path | Use it for |
| --- | --- | --- |
| GET | `/api/health` | Is the API up and connected to the database? |
| GET | `/api/parks?search=` | Park list; `search` matches name, state or code |
| GET | `/api/parks/{park_code}` | One park: name, state, coordinates, description, weather point |
| GET | `/api/weather/predict?park_code=&date=&activity=` | **The main call.** Weather + suitability for one park on one date |
| POST | `/api/weather/compare` | The same for 2–5 parks on one date, ranked best first |
| GET | `/api/weather/best-time/{park_code}` | Twelve months: typical weather, scores for every activity, best months |
| GET | `/api/weather/seasonal/{park_code}` | Monthly averages straight from the historical data |
| GET | `/api/weather/history/{park_code}?start_date=&end_date=` | Daily observations (max 3 years per call) |
| GET | `/api/models/performance` | Model accuracy, for an "about the data" page |

### `GET /api/weather/predict`

```bash
curl "https://YOUR-API/api/weather/predict?park_code=zion&date=2027-04-15&activity=hiking"
```

```json
{
  "park": {"park_code": "zion", "park_name": "Zion National Park", "state": "UT",
           "latitude": 37.2, "longitude": -112.99,
           "weather_location_note": "Weather point: Zion Canyon Visitor Center (NPS visitor center)."},
  "travel_date": "2027-04-15",
  "days_ahead": 165,
  "activity": "hiking",
  "prediction_type": "climate_estimate",
  "model_name": "seasonal_regression",
  "source": "ParkWise climate model: Seasonal regression with trend (Open-Meteo history 2015–2025)",
  "units": {"temperature": "celsius", "precipitation": "mm", "wind_speed": "km/h"},
  "temperature": {"max_c": 19.6, "min_c": 4.3, "max_range_c": [13.7, 25.8], "min_range_c": [0.4, 8.9],
                  "range_note": "80% range, set from this model's past errors at this park in this month."},
  "precipitation": {"probability": 0.184, "kind": "climate_model_probability",
                    "wet_day_threshold_mm": 1.0, "expected_mm": null},
  "snow": {"probability": 0.0},
  "wind": {"max_kmh": 19.6},
  "suitability": {"score": 93.6, "label": "Excellent",
                  "components": {"temperature": 100.0, "precipitation": 81.6, "wind": 100.0, "snow": 100.0},
                  "weights": {"temperature": 0.4, "precipitation": 0.35, "wind": 0.15, "snow": 0.1},
                  "notes": []},
  "summary": "Typical for mid April at Zion National Park (2015–2025): highs around 20 °C (14 to 26), …",
  "uncertainty": "This is not a forecast. …",
  "notes": [],
  "generated_at": "2026-11-01T20:00:00+00:00"
}
```

| Field | Meaning |
| --- | --- |
| `prediction_type` | `forecast` or `climate_estimate`. Label it in your UI. |
| `temperature.max_c` / `min_c` | Expected daily high and low. |
| `temperature.*_range_c` | Likely range. For climate estimates it's an 80% range from the model's past errors at that park and month (on test years it held 78% of the time). For forecasts it's a rule of thumb that widens with lead time. |
| `precipitation.probability` | 0–1. Forecast: chance of precipitation. Climate estimate: share of days that are wet (≥ 1 mm). `kind` says which. |
| `precipitation.expected_mm` | Forecast only: expected amount. `null` for climate estimates. |
| `snow.probability` | 0–1 chance of a snow day (≥ 1 cm). |
| `wind.max_kmh` | Typical (or forecast) strongest wind of the day. |
| `suitability.score` / `label` | 0–100 and Excellent (80+), Good (65+), Fair (45+), Poor. `components` and `weights` explain it. |
| `notes` | Warnings worth showing, e.g. dangerous heat or likely snow. |
| `summary`, `uncertainty` | Ready-made sentences in °C, if you don't want to write your own. |

If the live forecast is down, a near-term date quietly gets a climate estimate instead, and `notes`
says so. Every answer is logged in the `weather_predictions` table.

### `POST /api/weather/compare`

```bash
curl -X POST "https://YOUR-API/api/weather/compare" -H "Content-Type: application/json" \
     -d '{"park_codes": ["zion", "yose", "acad"], "date": "2027-05-20", "activity": "hiking"}'
```

Returns `{"travel_date", "activity", "best_park_code", "results": [...]}`, where each result is a
full `/predict` response plus `rank` (1 = best score). 2–5 distinct parks.

### `GET /api/weather/best-time/{park_code}`

Returns `best_months` (the three best months for each activity, best first) and `months`, twelve
entries with `temp_max_c`, `temp_min_c`, `wet_probability`, `snow_probability`, `wind_max_kmh`,
`scores` and `labels` for every activity, and `year_to_year` (the coolest and warmest year's average
high, and the driest and wettest year's share of wet days).

## Errors

Every error has the same shape, so one handler covers them all:

```json
{"error": {"code": "not_found", "message": "No park with code 'nope'.", "details": null}}
```

| HTTP | `code` | When | What to do |
| --- | --- | --- | --- |
| 400 | `invalid_request` | Date in the past or more than 3 years ahead; history range too long; the same park twice in a comparison | Show `message` to the user |
| 404 | `not_found` | Unknown park code or path | Check the code against `/api/parks` |
| 422 | `validation_error` | Missing or malformed parameter (bad date, unknown activity) | `details` lists each problem |
| 503 | `model_not_ready` | The server has no trained model | Server-side problem: tell the weather team |
| 500 | `internal_error` | Bug | Retry later. Details are hidden in production. |

## Calling it from a website

The API only accepts browser requests from origins listed in Render's `CORS_ORIGINS` (see
[DEPLOYMENT.md](DEPLOYMENT.md#5-connect-the-two)). Send the weather team your site's URL to be added.
Server-to-server calls (no browser) aren't affected by CORS.

```js
const API = "https://YOUR-API";

async function getWeather(parkCode, date, activity = "hiking") {
  const url = new URL("/api/weather/predict", API);
  url.search = new URLSearchParams({ park_code: parkCode, date, activity });
  const response = await fetch(url);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error.message);
  return body;
}

const w = await getWeather("zion", "2027-04-15");
console.log(`${w.prediction_type}: high ${w.temperature.max_c} °C, ${w.suitability.label}`);
```

A React app can reuse this project's pieces: `frontend/src/services/api.js` (the client, with
`ApiError`), `components/PredictionCard.jsx` (the full results card), `ScoreBadge.jsx` and
`PredictionTypeTag.jsx`. They use the Tailwind theme in `frontend/src/index.css`.

## Calling it from Python

Over HTTP, from any service:

```python
import requests

r = requests.get("https://YOUR-API/api/weather/predict",
                 params={"park_code": "yose", "date": "2027-06-01", "activity": "camping"}, timeout=90)
r.raise_for_status()
print(r.json()["suitability"])
```

Use a generous timeout: the free Render instance sleeps after 15 minutes idle, and the first request
then takes 30–60 seconds.

In-process, from code inside `backend/` (same database):

```python
from datetime import date

from app.database.connection import SessionLocal
from app.services.weather_service import predict_weather, compare_parks, best_time

with SessionLocal() as db:
    outlook = predict_weather(db, "yose", date(2027, 6, 1), "camping")
```

The function raises `NotFoundError`, `InvalidRequestError` or `ModelNotReadyError` from
`app.services.errors` instead of returning HTTP errors.

## Performance and limits

- Typical response time once awake: 5–50 ms for climate estimates and database calls, about
  0.3–1 s for a forecast (it calls Open-Meteo). Forecasts are cached for an hour per park.
- A compare call is one prediction per park.
- There's no API key or rate limit on this API. Open-Meteo's free tier is the real limit for
  forecasts (about 10,000 calls a day), and the one-hour cache keeps usage far below it.

## Versioning

`/api/health` reports `api_version`. Fields are only ever added within a version. Removing or renaming
a field means a new version, announced to the team first.
