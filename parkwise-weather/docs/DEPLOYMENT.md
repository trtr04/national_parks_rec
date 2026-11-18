# Deploying ParkWise Weather

Three free services, each doing one job:

```text
 Browser ──► Vercel (React site, frontend/) ──fetch──► Render (FastAPI, backend/) ──SQL──► Neon (PostgreSQL)
                                                          │
                                                          └── loads trained_models/climate_model.joblib from the repo
```

| Service | Hosts | Free-tier behaviour to know about |
| --- | --- | --- |
| [Neon](https://neon.tech) | PostgreSQL: parks + 253k days of weather (~40 MB) | Pauses when idle; the first query after a pause takes about a second. |
| [Render](https://render.com) | The API | Sleeps after 15 minutes without traffic; the next request takes 30–60 s to wake it. |
| [Vercel](https://vercel.com) | The website | Static files on a CDN; always fast. |

Nothing in production trains models or downloads weather history. The model file is committed to the
repository, and the weather history is copied once from your local database. Production only needs
the internet for the live 16-day forecast from Open-Meteo.

Allow about 30 minutes. You need a GitHub account; Neon, Render and Vercel can all sign in with GitHub.

---

## 0. Before you start

From `backend/` with the virtual environment active, check that everything is green locally:

```bash
pytest -q                          # backend tests
python -m scripts.validate_data    # ends with Result: PASS
cd ../frontend && npm test && npm run build
```

## 1. Put the code on GitHub

Render and Vercel deploy from a GitHub repository. From the project root:

```bash
git init
git add .
git status        # check: no .env, no data/parkwise.db, no node_modules, no .venv
git commit -m "ParkWise Weather"
```

Then create an **empty** repository on GitHub (no README or .gitignore) and follow GitHub's
"push an existing repository" commands, usually:

```bash
git remote add origin https://github.com/YOUR-NAME/parkwise-weather.git
git branch -M main
git push -u origin main
```

`.gitignore` keeps secrets (`.env`) and the local database out of Git. The trained model
(`trained_models/climate_model.joblib`, ~400 KB) and `metrics.json` **are** committed on purpose:
the API loads them at startup.

After the push, the **Actions** tab on GitHub runs CI (`.github/workflows/parkwise-weather-ci.yml` at the repository root): backend tests on
SQLite and PostgreSQL, a check that the committed model loads, and the frontend tests and build.

## 2. Neon: the database

1. Sign in at neon.tech → **New project**. Name it `parkwise`, pick the region closest to your
   Render region (e.g. US East (Ohio) for Render Ohio, US West (Oregon) for Render Oregon), PostgreSQL 17.
2. On the project dashboard, **Connect** → copy the connection string. Use the **direct**
   connection, i.e. turn **Connection pooling off** (the host has no `-pooler` in it). It looks like:

   ```text
   postgresql://neondb_owner:PASSWORD@ep-something-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

   Treat it like a password: don't commit it or paste it in chat.

3. Copy your local data into Neon (about a minute). From `backend/`:

   ```bash
   python -m scripts.copy_to_postgres --target "PASTE-THE-NEON-URL-HERE"
   ```

   It creates the tables, then upserts 63 parks and 253,134 days of weather. It's safe to re-run,
   for example after loading more data locally.

4. Optional check that the data arrived (prints `Result: PASS` against Neon):

   ```bash
   DATABASE_URL="PASTE-THE-NEON-URL-HERE" python -m scripts.validate_data | tail -1
   ```

   This also overwrites `data/validation_report.md` with Neon's report. The contents are the same.

## 3. Render: the API

1. Sign in at render.com → **New** → **Blueprint** → connect GitHub and pick the repository.
   Set **Blueprint Path** to `parkwise-weather/render.yaml`. Render reads it and proposes a free web service called `parkwise-weather-api`.
2. It asks for the values marked `sync: false`:

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | The Neon connection string from step 2 |
   | `CORS_ORIGINS` | For now `http://localhost:5173`. You'll replace it after step 4. |
   | `CORS_ORIGIN_REGEX` | Leave empty (see "Preview deployments" below) |

   `PYTHON_VERSION` and `ENVIRONMENT=production` are already set by the Blueprint.
3. **Apply**. The first build takes a few minutes (installing pandas and scikit-learn).
4. When it says **Live**, open `https://YOUR-SERVICE.onrender.com/api/health`. You should see:

   ```json
   {"status": "ok", "environment": "production",
    "database": {"connected": true, "dialect": "postgresql", "park_count": 63, "weather_rows": 253134}}
   ```

   and `/docs` shows the interactive API documentation.

## 4. Vercel: the website

1. Sign in at vercel.com → **Add New** → **Project** → import the repository.
2. **Root Directory**: click **Edit** and choose `parkwise-weather/frontend`. Vercel detects Vite; `frontend/vercel.json`
   sets the build command, the output folder and the rewrite that makes page reloads work on
   routes like `/compare`.
3. **Environment Variables**: add

   | Name | Value |
   | --- | --- |
   | `VITE_API_BASE_URL` | `https://YOUR-SERVICE.onrender.com` (no trailing slash) |

4. **Deploy**. Note the production URL, e.g. `https://parkwise-weather.vercel.app`.

`VITE_` variables are baked into the JavaScript at build time. If you change one, redeploy
(Deployments → ⋯ → Redeploy).

## 5. Connect the two

The API only answers browsers on origins it trusts (CORS). In Render → the service → **Environment**,
set `CORS_ORIGINS` to the Vercel URL, without a trailing slash:

```text
https://parkwise-weather.vercel.app
```

Several origins are comma-separated, e.g. a custom domain as well. Saving restarts the service.

### Preview deployments (optional)

Vercel gives each branch and pull request its own URL, such as
`https://parkwise-weather-git-new-chart-yourname.vercel.app`. To let those call the API too, set
`CORS_ORIGIN_REGEX` on Render to match your project's URLs, for example:

```text
^https://parkwise-weather(-[a-z0-9-]+)?\.vercel\.app$
```

Keep the pattern specific to your project name. A pattern like `.*\.vercel\.app` would let any
Vercel site call your API.

## 6. Check the live site

- [ ] The footer dot is green: "API 0.1.0 connected to postgresql. 63 parks, 253,134 weather days stored."
      (If Render was asleep, the first load can take up to a minute.)
- [ ] Home: a date in the next two weeks says **Forecast**; a later date says **Climate estimate**
- [ ] Compare, Best time to visit, Weather history and Model insights all show data
- [ ] Reloading the browser on `/compare` still shows the page, not a 404
- [ ] In the browser's developer tools (Console), no CORS errors

## Updating the live site

| You changed | Do this |
| --- | --- |
| Code | Push to `main`. Render and Vercel both redeploy automatically. |
| The model | `python -m scripts.train_models` locally, commit `trained_models/`, push. The API picks up the new file on deploy. |
| Weather data | Load it locally, then `python -m scripts.copy_to_postgres --target "NEON-URL"` again. |
| scikit-learn version | Change the pin in `backend/requirements.txt`, retrain, commit both. CI fails if the committed model was trained with a different version. |

## Troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| Footer: "can't reach the ParkWise API" | Render is waking up (wait a minute), or `VITE_API_BASE_URL` is wrong or missing. Fix it in Vercel and **redeploy**. |
| Console: `blocked by CORS policy` | `CORS_ORIGINS` on Render doesn't exactly match the site's address (scheme, no trailing slash). |
| `/api/health` says `"status": "degraded"` | Render can't reach Neon. Check `DATABASE_URL`, including `?sslmode=require`. |
| Predictions return 503 `model_not_ready` | `trained_models/climate_model.joblib` isn't in the repository. Commit it and push. |
| Render build fails installing packages | Make sure `PYTHON_VERSION` is `3.13.5` (set by `render.yaml`). |
| Render log: "trained with scikit-learn X but Y is installed" | The pin in `requirements.txt` and the model disagree. Retrain locally and commit. |
| Page reload on `/compare` gives Vercel's 404 | The Vercel project's Root Directory isn't `parkwise-weather/frontend`, so `vercel.json` isn't used. |
