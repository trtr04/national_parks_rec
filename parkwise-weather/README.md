# ParkWise Weather

The weather module of **ParkWise — AI-Powered National Park Travel Planner** (AI Collective project).
It gives a weather outlook for a national park on a travel date: a real forecast for the next 16
days, and a clearly labelled historical climate estimate for anything further out.

**Status: Phase 5 — ready to deploy.** Data pipeline, forecasting models and website work end to end, tested on SQLite and PostgreSQL, with CI and deployment configs for Neon, Render and Vercel. Step-by-step: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). For teammates using the API: [docs/INTEGRATION.md](docs/INTEGRATION.md).

---

## 1. Architecture

```text
 Browser (React + Vite + Tailwind + Recharts)          frontend/
     │   fetch("/api/...")   — all calls go through src/services/api.js
     ▼
 FastAPI (Python)                                       backend/app/
     api/        routes: parse + validate HTTP input (Pydantic)
     services/   business logic: queries, predictions, scoring
     database/   SQLAlchemy engine, tables, schema.sql
     ▼
 SQL database   SQLite locally  →  PostgreSQL (Neon) in production

 scripts/ ETL      ── NPS API ──────────────► parks
                   └─ Open-Meteo archive ────► weather_history (2015–2025)
 scripts/train_models (scikit-learn) ────────► trained_models/
 /predict  ── ≤ 15 days ahead: Open-Meteo Forecast API (live)
           └─ later: trained climate model ──► weather_predictions (every answer logged)
```

Why it's split this way:

| Decision | Reason |
| --- | --- |
| Routes in `api/`, logic in `services/` | Teammates can `import predict_weather` in Python without running a server, and the logic is testable on its own. |
| One `api.js` in the frontend | Pages never build URLs themselves. If an endpoint changes, one file changes. |
| SQLAlchemy ORM + a raw `schema.sql` | ORM keeps the code identical for SQLite and Postgres; `schema.sql` documents the design and creates it on Neon. |
| Metric units in the DB | Open-Meteo returns °C, mm, cm, km/h. Store as received, convert on screen (°F, inches). No rounding drift. |
| Every error is `{"error": {"code", "message", "details"}}` | The frontend and teammates handle one error shape everywhere. |
| The API serves a saved model file | Training is slow and offline (`scripts/train_models`); the API only loads `trained_models/climate_model.joblib`, so requests stay fast. |

## 2. Folder structure

```text
parkwise-weather/
├── frontend/
│   ├── public/favicon.svg
│   ├── src/
│   │   ├── components/   Layout, Navbar, Footer, BackendStatus, ParkPicker,
│   │   │                 HeroLandscape, StateMessage, PageHeader, ActivityPicker,
│   │   │                 PredictionCard, PredictionTypeTag, ScoreBadge
│   │   ├── pages/        WeatherExplorer, HistoryDashboard, ComparePage,
│   │   │                 BestTimePage, ModelInsightsPage, NotFoundPage
│   │   ├── services/     api.js (backend calls), useApi.js (loading/error hook), units.js, dates.js
│   │   ├── App.jsx       routes
│   │   ├── main.jsx      entry point
│   │   ├── test/         Vitest setup and fixtures (tests sit next to their files: *.test.js[x])
│   │   └── index.css     Tailwind + design tokens
│   ├── index.html, package.json, vite.config.js, vercel.json, .env.example
├── backend/
│   ├── app/
│   │   ├── api/          health.py, parks.py, weather.py, model_performance.py
│   │   ├── database/     connection.py, models.py (ORM tables), schema.sql, upsert.py
│   │   ├── models/       schemas.py (Pydantic request/response shapes)
│   │   ├── services/     park_service.py, weather_service.py (predict/compare), errors.py,
│   │   │                 climate_models.py (the 3 models), suitability.py, forecast_client.py,
│   │   │                 model_store.py (loads the trained model), analytics_service.py (SQL)
│   │   ├── config.py     settings from .env
│   │   └── main.py       FastAPI app, CORS, error handlers
│   ├── scripts/          init_db.py, seed_dev_parks.py, load_parks.py, load_weather_history.py,
│   │                     validate_data.py, train_models.py, copy_to_postgres.py, http_client.py
│   ├── tests/            conftest.py, synthetic.py, test_api.py, test_etl.py, test_predictions.py
│   ├── pytest.ini, .python-version, requirements.txt (server), requirements-dev.txt (+ tests, notebook)
├── data/                 SQLite file (git-ignored), etl_weather.log, validation_report.md
├── notebooks/            01_eda.ipynb (exploratory analysis, executed with outputs)
├── trained_models/       climate_model.joblib, metrics.json (committed: the deployed API loads them)
├── docs/                 DEPLOYMENT.md (Neon + Render + Vercel), INTEGRATION.md (API guide for teammates)
├── .github/workflows/    ci.yml (tests on SQLite + PostgreSQL, frontend tests + build)
├── render.yaml           Render Blueprint for the API
├── .env.example, .gitignore, README.md
```

> "models" appears twice: `app/database/models.py` = database tables, `app/models/schemas.py` =
> JSON shapes. Machine-learning models live in `app/services/climate_models.py` and `trained_models/`.

## 3. Database schema

Three tables (full DDL in `backend/app/database/schema.sql`):

```text
parks                         weather_history                      weather_predictions
─────────────────────         ──────────────────────────────       ─────────────────────────────
park_code   PK                park_code  PK, FK → parks            prediction_id  PK
park_name                     date       PK                        park_code      FK → parks
state                         temp_max, temp_min        (°C)       target_date
latitude, longitude           precipitation, rainfall   (mm)       prediction_generated_at
description                   snowfall                  (cm)       prediction_type  forecast | climate_estimate
weather_location_note         wind_speed_max            (km/h)     model_name, activity
data_source, updated_at                                            predicted_temp_max / _min
                                                                   precipitation_probability  0–1
                                                                   weather_suitability_score  0–100
```

Constraints that protect data quality:

- **Composite primary key `(park_code, date)`** — the same day can't be stored twice, so the ETL can be re-run safely.
- **Foreign keys with `ON DELETE CASCADE`** — no weather rows for parks that don't exist.
- **CHECK constraints** — latitude/longitude in range, precipitation/snow/wind ≥ 0, `temp_min ≤ temp_max`,
  `prediction_type` is one of two values, probability 0–1, score 0–100.
- **Indexes** — `weather_history(date)` for cross-park date queries; `weather_predictions(park_code, target_date)`.

`weather_location_note` exists because big parks span huge elevation ranges. Each park's weather
comes from one representative visitor-accessible point, and the note says which.

## 4. Setup and run (macOS)

You need **Python 3.10+** and **Node.js 20+** (`node --version`; install from nodejs.org if missing).

### Backend — terminal 1

```bash
cd ~/Documents/parkwise-weather
cp .env.example .env                 # then put your NPS_API_KEY in it

cd backend
python3 -m venv .venv
source .venv/bin/activate            # prompt now starts with (.venv)
pip install -r requirements-dev.txt

pytest -v                            # run the tests first
python -m scripts.init_db            # create tables in data/parkwise.db
```

Load the data and train the model (Phases 2–3, one time):

```bash
python -m scripts.load_parks             # 63 National Parks from the NPS API (~5 s)
python -m scripts.load_weather_history   # 2015–2025 daily weather from Open-Meteo (~30 min)
python -m scripts.validate_data          # writes data/validation_report.md
python -m scripts.train_models           # trains, evaluates, saves trained_models/ (~1 min)
```

`load_weather_history` respects Open-Meteo's free rate limits. It waits out per-minute and
per-hour limits by itself; if it hits the daily limit it stops, and running it again the
next day continues where it left off (completed park-years are skipped).

Then start the API:

```bash
uvicorn app.main:app --reload --port 8000
```

Open http://127.0.0.1:8000/docs for interactive API docs.

### Frontend — terminal 2

```bash
cd ~/Documents/parkwise-weather/frontend
npm install
npm run dev
```

Open http://localhost:5173. In development Vite forwards `/api/*` to port 8000, so no extra config.

### Optional: PostgreSQL instead of SQLite

Copy the local data into any PostgreSQL database (Neon, or one on your machine), then point `.env` at it:

```bash
python -m scripts.copy_to_postgres --target "postgresql://USER:PASS@HOST/DB?sslmode=require"
# then in .env:
DATABASE_URL=postgresql://USER:PASS@HOST/DB?sslmode=require
```

To run the backend tests against PostgreSQL, set `TEST_DATABASE_URL` to an **empty, throwaway**
database (the tests wipe it): `TEST_DATABASE_URL=postgresql://… pytest -q`.

### Deploying

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): Neon (database), Render (API, from `render.yaml`) and
Vercel (website, from `frontend/vercel.json`), about 30 minutes on free tiers.

## 5. Verification checklist

Backend
- [ ] `pytest -q` → **51 passed** (also with `TEST_DATABASE_URL` pointing at PostgreSQL) (no network needed: the forecast is faked and the test model is trained on synthetic data)
- [ ] `python -m scripts.load_parks` prints `Loaded 63 National Parks into the parks table.`
- [ ] `python -m scripts.validate_data` ends with `Result: PASS`
- [ ] `python -m scripts.train_models` prints a table of 3 models and the selected one
- [ ] http://127.0.0.1:8000/api/health shows `"park_count": 63` and about 253,000 `weather_rows`
- [ ] `/api/weather/predict?park_code=yose&date=<a date 3+ weeks out>&activity=hiking` returns `"prediction_type": "climate_estimate"` with ranges and a suitability score
- [ ] The same with a date in the next two weeks returns `"prediction_type": "forecast"`
- [ ] `activity=surfing` returns 422 `validation_error`; `park_code=nope` returns 404 `not_found`
- [ ] `/api/models/performance` returns validation and test metrics for all 3 models

Frontend
- [ ] `npm test` (in `frontend/`) → **16 passed**; `npm run build` finishes without warnings

Frontend ↔ backend
- [ ] Footer status dot is green: "API 0.1.0 connected to sqlite. 63 parks, … weather days stored."
- [ ] Park search lists all 63 parks; typing "zi" filters to Zion
- [ ] Choosing a date in the next 16 days (today to today + 15) says "forecast"; later says "climate estimate"
- [ ] A valid submission shows the results card: forecast/climate-estimate tag, high and low in °F with ranges, wet days, wind, score and why
- [ ] Adding a "Leaving" date shows one card per trip day (up to 14); clicking a day opens its full card
- [ ] Compare → add 2–5 parks, a date and an activity → parks ranked by score, plus a month-by-month season chart
- [ ] Best time → pick a park → best three months, a 12-month score chart and a month-by-month table; switching activity re-scores instantly
- [ ] Model insights → model table, predicted-vs-actual scatter, error histogram, error by month, most/least predictable parks
- [ ] History page → pick a park → charts of real 2025 data

## 6. API (for teammates)

Base URL: `http://127.0.0.1:8000` locally. Full, always-current docs: `/docs`. Response fields,
error codes and code examples for other teams: [docs/INTEGRATION.md](docs/INTEGRATION.md).

| Method | Path | Status |
| --- | --- | --- |
| GET | `/api/health` | ✅ API + database status |
| GET | `/api/parks?search=` | ✅ list parks |
| GET | `/api/parks/{park_code}` | ✅ one park |
| GET | `/api/weather/history/{park_code}?start_date=&end_date=` | ✅ daily rows, 2015–2025 |
| GET | `/api/weather/seasonal/{park_code}` | ✅ monthly climate summary, aggregated in SQL |
| GET | `/api/weather/predict?park_code=&date=&activity=` | ✅ forecast (≤ 15 days ahead) or climate estimate, with suitability |
| POST | `/api/weather/compare` `{park_codes, date, activity}` | ✅ 2–5 parks ranked by suitability |
| GET | `/api/weather/best-time/{park_code}` | ✅ 12 months: typical weather, score for every activity, year-to-year spread, best months |
| GET | `/api/models/performance` | ✅ MAE / RMSE / Brier for every model, validation and test, plus chart data |

`/predict`, `/compare` and `/best-time` answer 503 `model_not_ready` until `scripts.train_models` has been run.

Python, without HTTP: `from app.services.weather_service import predict_weather` — the return
shape is documented in its docstring. Example (trimmed):

```json
{
  "park": {"park_code": "zion", "park_name": "Zion National Park", "...": "..."},
  "travel_date": "2027-04-15", "days_ahead": 165, "activity": "hiking",
  "prediction_type": "climate_estimate", "model_name": "seasonal_regression",
  "temperature": {"max_c": 19.6, "min_c": 4.3, "max_range_c": [13.7, 25.8], "min_range_c": [0.4, 8.9]},
  "precipitation": {"probability": 0.184, "kind": "climate_model_probability", "wet_day_threshold_mm": 1.0},
  "snow": {"probability": 0.0}, "wind": {"max_kmh": 19.6},
  "suitability": {"score": 93.6, "label": "Excellent", "components": {"...": "..."}},
  "summary": "Typical for mid April at Zion National Park (2015–2025): highs around 20 °C (14 to 26), lows around 4 °C. Rain or snow on about 1 day in 5. Excellent for hiking (94/100).",
  "uncertainty": "This is not a forecast. ..."
}
```

## 7. Data and models

### Data (Phase 2)

- **Parks:** the 63 National Parks from the NPS API (`scripts/load_parks.py`). Sequoia and Kings
  Canyon share one NPS code (`seki`). Each park's weather point is a main visitor center, so the
  weather describes where visitors actually go; `weather_location_note` says which one. Only Kobuk
  Valley, which has no visitor center near the park, uses the park centre.
- **Weather:** daily highs, lows, precipitation, rain, snowfall and maximum wind from the Open-Meteo
  archive (ERA5 reanalysis), 2015–2025, one request per park per year (`scripts/load_weather_history.py`).
  About 253,000 rows when complete.
- **Validation:** `scripts/validate_data.py` checks coverage, date gaps, missing values, the table
  rules and physically plausible ranges, and writes `data/validation_report.md`.
- **Analytical SQL:** `app/services/analytics_service.py`: driest parks per month (CTE + `RANK()`),
  year-over-year trend per park (`LAG()` + rolling `AVG()`), and date gaps (`LAG()`).

### Exploratory analysis

`notebooks/01_eda.ipynb` (executed, with charts). What it found, and what that means for the models:

| Finding | Consequence |
| --- | --- |
| The seasonal cycle of daily highs spans 23 °C (median park), from 1.4 °C (American Samoa) to 33 °C (Voyageurs) | Every model is built around the time of year |
| A single day's high is 3.2 °C from its seasonal normal on average | That's roughly the best any months-ahead estimate can do |
| Anomalies barely persist: correlation 0.08 after 14 days | Climate estimates can't use recent weather; they use date and place only |
| Highs rose about 0.24 °C per decade across parks | Small, but worth a trend term |

### Models (Phase 3)

Three models (`app/services/climate_models.py`) predict a day's high, low and chance of a wet day (≥ 1 mm):

| Model | How it works |
| --- | --- |
| `seasonal_average` (baseline) | Per park and day of year: the average of the training years within ±7 days |
| `seasonal_regression` | Per park: regression on three yearly sine/cosine pairs. Plus one warming trend shared by all parks (10 years is too short to trust each park's own trend). Logistic regression for wet days |
| `random_forest` | One model across all parks: location, season, the park's climatology for that day, year |

Chronological split: train 2015–2021, validation 2022–2023 (chooses the model), test 2024–2025
(reported once). Results from `python -m scripts.train_models`, all 63 parks:

| Model | Test high MAE | Test low MAE | Test high RMSE | Test wet-day Brier | Validation score |
| --- | --- | --- | --- | --- | --- |
| seasonal_average | 3.36 °C | 2.94 °C | 4.46 °C | 0.1817 | 3.000 |
| **seasonal_regression** (selected) | **3.35 °C** | **2.94 °C** | **4.44 °C** | **0.1799** | **2.956** |
| random_forest | 3.42 °C | 2.98 °C | 4.55 °C | 0.1837 | 3.018 |

The validation score adds each metric divided by the baseline's (the baseline is 3.0; lower is
better). The models are close because the floor is the weather's own day-to-day noise (above); the
regression wins on every test metric, and the forest doesn't beat the simple baseline. Errors are
smallest for tropical parks (0.6 °C at American Samoa, 1.1 °C at the Virgin Islands) and largest on
the northern Great Plains (5.3 °C at Theodore Roosevelt), and smaller in summer (2.5 °C) than in
winter (4.6 °C).

**Ranges.** Each climate estimate comes with an 80% range for the high and the low, taken from the
selected model's errors for that park and month when each year is predicted by a model that never
saw it. On the test years the ranges contained 78% of highs and 79% of lows.

### Suitability score

`app/services/suitability.py` scores a day 0–100 for hiking, camping, sightseeing or wildlife
watching. It combines four 0–100 parts with activity-specific weights: temperature (a comfortable
band for the daytime high, minus 6 points per °C outside it; camping also penalises nights below
5 °C), precipitation (chance of a dry day), wind (full marks up to 20 km/h, zero at 60 km/h) and
snow. A high of 38 °C or more caps hiking and camping at 30. Labels: 80+ Excellent, 65+ Good, 45+
Fair, otherwise Poor. The weights are judgement calls, kept in one file so they're easy to tune.

## 8. Roadmap

- ✅ **Phase 2 — Data + SQL:** NPS API loader (identify the 63 National Parks, choose weather points),
  Open-Meteo ETL for 2015–2025 with retries, logging and upserts, analytical SQL queries
  (CTEs, window functions), data validation report.
- ✅ **Phase 3 — Models:** EDA, seasonal-average baseline, seasonal regression, random forest,
  chronological train/validation/test, MAE/RMSE/Brier, suitability score, real `predict_weather()`.
- ✅ **Phase 4 — Website:** results card and day-by-day trip view, park comparison with season chart,
  best-time-to-visit (monthly scores per activity, year-to-year spread), model insights charts.
- ✅ **Phase 5 — Tests + deployment:** PostgreSQL support verified (tests, analytics SQL, validation),
  `copy_to_postgres` for loading Neon, frontend tests (Vitest), GitHub Actions CI, `render.yaml`,
  `vercel.json`, deployment and integration guides. Going live needs your own Neon, Render and Vercel
  accounts: follow docs/DEPLOYMENT.md.

## 9. Notes

**Images.** The hero is an SVG illustration, so there are no licensing questions yet. If you add
park photos later, use ones with a clear licence (e.g. NPS photos marked public domain, or
Unsplash/Wikimedia Commons with their stated licence) and add credits in the footer. Not every
photo on nps.gov is public domain; check each one.

**Troubleshooting**
- *Footer says it can't reach the API* → is uvicorn running on port 8000? Did you start it from `backend/`?
- *`ModuleNotFoundError: app`* → run commands from the `backend/` folder with the venv activated.
- *Port 8000 in use* → `lsof -i :8000` then stop that process, or run uvicorn on 8001 and change `vite.config.js`.
- *CORS error in the browser console* → add your frontend's exact origin to `CORS_ORIGINS` in `.env`.
- *Reset the local database* → delete `data/parkwise.db` and rerun `init_db` + `seed_dev_parks`.
