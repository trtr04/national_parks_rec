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
python3 scripts/build_catalog.py       # parks, trails, photos -> data/processed/
python3 -m pytest
```

`fetch_nps_content.py` reads the `NPS_API_KEY` environment variable and falls
back to the shared, rate-limited `DEMO_KEY`. The curated route list and its
hand-checked distance, gain, and time values live in
`config/trail_catalog.json`.

ParkMatch is a student project and is not affiliated with the National Park
Service.
