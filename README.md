# ParkMatch

Trail discovery prototype for Mount Rainier National Park. See
`ParkMatch_PRD_v0.1_EN.md` for scope and `docs/geometry_pipeline.md` for the
route-geometry workflow.

## Run the app

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Rebuild the data

```bash
python3 scripts/fetch_nps_content.py   # raw NPS API records -> data/raw/nps_api/
python3 scripts/fetch_wa_trails.py     # Washington trail lines -> data/raw/
python3 scripts/build_routes.py        # one route line per hike -> data/processed/
python3 scripts/build_catalog.py       # parks, trails, photos -> data/processed/
python3 -m pytest
```

`fetch_nps_content.py` reads the `NPS_API_KEY` environment variable and falls
back to the shared, rate-limited `DEMO_KEY`. The curated route list and its
hand-checked distance, gain, and time values live in
`config/trail_catalog.json`.

Route lines come from the Washington State Trails Database. Which segments
make up each hike is listed by hand under `route` in
`config/trail_catalog.json`; `data/processed/route_checks.csv` compares each
line with the official distance. All lines are provisional and are not for
navigation.

ParkMatch is a student project and is not affiliated with the National Park
Service.
