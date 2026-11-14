# ParkMatch — National Park & Hiking Trail Discovery

**Product Requirements Document (PRD)**  
**Version:** 0.3 (working draft)  
**Last updated:** November 13, 2026  
**Team:** Three members; Tracy leads the Hiking Trails / Trail Discovery & Recommendation component  
**Current status:** A working local Streamlit prototype covers 10 Mount Rainier hikes with top-three matching, a clickable map, and photo galleries. Only one route has a line on the map, and it is provisional; trail attributes, scenery tags, and photos still need human review. Not deployed; no user testing yet

> **Status key:** ✅ Completed or confirmed · 🟡 Explored, attempted, or partially complete · ⬜ Planned. A discussed feature is **not** an implemented feature. Illustrative figures and proposed structures should not be presented as verified results.

## 1. Project Overview

### 1.1 Product summary

**ParkMatch** is an interactive national park and hiking-trail discovery platform that recommends destinations and hiking routes based on structured user preferences. Users select their departure location, budget, interests, hiking ability, and available time from predefined options. ParkMatch returns a short list of explainable recommendations and helps users preview each hike using an interactive route map, basic trail details, and a small photo gallery.

### 1.2 Problem and value proposition

People planning a national park trip often need to search multiple websites to find out whether a destination is affordable, whether a hike matches their ability and schedule, and what scenery they can expect. ParkMatch combines **preference-aware recommendations** with **visual trail exploration** in one straightforward experience.

### 1.3 Target users

- First-time national park visitors who are unfamiliar with individual parks and routes.
- Hikers who know their available time, preferred difficulty, and scenery interests but do not know which route to choose.
- Travelers planning short trips from a known origin city, particularly in the Mount Rainier pilot.

### 1.4 V1 scope and strategy

- **Pilot park:** Mount Rainier National Park (NPS park code `MORA`).
- **Initial data proof:** Three manually verified, complete hiking routes with attributes, geometry, and image references.
- **Functional MVP target:** Approximately 10–15 curated routes, subject to data availability and schedule.
- **Input:** Multiple-choice, dropdown, and checkbox controls; no open-ended text requirement.
- **Output:** Up to three trail recommendations, matching explanations, route distance, estimated duration, scenery tags, and elevation gain when available.
- **Exploration:** Zoomable, clickable route map; selecting a route shows a detail panel and a simple photo gallery.
- **Algorithm:** Rule-based eligibility filtering followed by configurable, explainable content-based scoring. Training a machine learning model is not required for V1.
- **Data storage:** CSV tables, GeoJSON geometry, and referenced or locally stored images. No database server is required for V1.
- **Expansion path:** Preserve a reusable park and trail schema so additional parks and a park-level recommendation stage can be added without redesigning the system.

### 1.5 Explicitly out of scope for V1

Nationwide complete-hike coverage; accounts, reviews, and saved lists; turn-by-turn GPS navigation; 3D/VR experiences; real-time trail cameras; automated reconstruction of all complete routes from GIS line segments; live lodging prices; complex learned recommendation models; and long-distance National Trails System routes as hikes in their own right (they appear only as a designation label where a curated day hike uses a section of one). `TRLSTATUS = 'Existing'` **must not** be interpreted as proof that a route is currently open.

## 2. User Journey and Functional Requirements

### 2.1 Intended user journey

1. **Set preferences:** Choose structured options for experience, difficulty, available time, desired scenery, and any supported trip-level constraints.
2. **Receive recommendations:** Filter out demonstrably unsuitable routes, rank eligible routes, and display up to three candidates with explanations.
3. **Explore a route:** Select or click a trail, highlight its geometry, and view route details and photos.
4. **Verify before visiting:** Open the relevant official NPS page for current access information, warnings, and conditions.

### 2.2 Proposed input fields

| Field | Control | Proposed choices | Role in V1 |
|---|---|---|---|
| Starting location | Dropdown or radio | Seattle, Tacoma, Olympia | Useful for eventual park-level travel costs and distance; does not inherently distinguish hikes within the same park. The prototype shows the straight-line distance to the park and does not use it in ranking. |
| Budget | Radio or dropdown | Low, medium, flexible; or well-defined dollar ranges | Park-level planning only until trustworthy cost assumptions are available. **Not in the prototype.** |
| Difficulty | Radio | Easy, moderate, hard | Trail eligibility and matching. The prototype treats the choice as the hardest level the user accepts; see section 6.1 for the draft label rule. |
| Available hiking time | Radio | Up to 2 hours; 2–4 hours; more than 4 hours | Eligibility and matching. The limits are inclusive, so a 2-hour hike fits "up to 2 hours". |
| Scenery interests | Multiselect | Mountain views, waterfalls, lakes, forests, wildflowers | Trail content matching. |

**Open decisions:** Define budget bands, whether to include maximum distance or route type, and how to handle unknown difficulty/duration. An input should not influence ranking unless a reliable supporting feature exists.

### 2.3 Feature requirements and acceptance criteria

| ID | Feature | Priority | V1 acceptance criterion |
|---|---|---|---|
| F01 | Structured preference form | Must | Users complete the form entirely with predefined options; the UI produces a consistent preferences object. |
| F02 | Curated trail catalog | Must | A working set of about 10 verified Mount Rainier hiking routes, with source references and explicit missing values. |
| F03 | Eligibility filtering and Top-3 ranking | Must | Consistent results for the same inputs; explainable scores; no forced recommendation when no route qualifies. |
| F04 | Interactive trail map | Must | Zoom and pan; select or click a route to highlight it and display its corresponding record. |
| F05 | Trail detail panel | Must | Show name, distance, duration, difficulty, scenery, and official source; elevation gain where known. |
| F06 | Photo gallery | Must | At most three approved, NPS-sourced photos per curated trail (one cover image plus up to two more); clear source/credit and a graceful missing-image state. No user-submitted content. |
| F07 | Basic park information | Should | Display park name, location, summary, official website, and relevant access notice/link. |
| F08 | Multi-park recommendation | Later | Add parks without rewriting the core schema or trail ranking interface. |
| F09 | Live conditions and advanced visualization | Later | Only after data reliability, permissions, and implementation effort have been assessed. |

## 3. Work Completed and EDA Progress

### 3.1 Dataset discovery and API investigation ✅

- Located the NPS Public Trails Geographic ArcGIS Feature Service and identified the relevant layer.
- Learned the distinction between Geographic Coordinate System and Web Mercator, and between a Map Image Layer and a Feature Layer.
- Inspected ArcGIS REST metadata and established that the trail layer has **layer ID 0**, leading to the query endpoint `/FeatureServer/0/query`.
- Diagnosed an initial `KeyError: 'features'`: the request was sent to the FeatureServer metadata endpoint rather than to the trail layer's query endpoint.
- Successfully requested the feature count using `returnCountOnly=true`: **31,377 trail feature records at the time of the query**.
- Important interpretation: 31,377 GIS features are **not** equivalent to 31,377 independent, complete hiking routes.

### 3.2 Retrieval and local storage 🟡

- Tried ArcGIS offset pagination using `resultOffset` and `resultRecordCount`; the server intermittently returned application-level `code: 500` / `Error performing query operation` after some batches.
- Investigated smaller batches and switched to retrieving IDs with `returnIdsOnly=true`, followed by small `objectIds` queries with delays, retries, and per-batch JSON files.
- **Checkpoint as of November 13, 2026:** `trail/trail_batches/` contains **314 saved batches**, and the combined `trail/nps_trails_partial.csv` holds **31,377 rows with 31,377 distinct `OBJECTID` values**. This exactly matches the 31,377 features counted earlier, so the attribute download is complete as of that count; a fresh `returnCountOnly` check against the live service has not been rerun, and the file name still says "partial".
- The initial saved attributes were requested using `returnGeometry=false`; therefore these files **do not contain the line geometry needed to draw routes**.
- Proposed local workflow: combine saved JSON attributes into a Pandas DataFrame, validate unique `OBJECTID` values, retain raw files, and save a separate cleaned CSV.

### 3.3 EDA activities and preliminary observations 🟡

| Topic | Work performed, proposed, or observed | Interpretation and limitation |
|---|---|---|
| Dataset structure | Used or prepared `head(10)`, `info()`, `describe(include='all')`, `value_counts()` | IDs are identifiers, not continuous measurements. |
| Missingness | Developed `isna()` checks and a plan to normalize `Unknown` and blank strings | Full-data missingness percentages have not been established. |
| Park counts | Explored / planned `UNITNAME × record count` bar charts | Partial downloads cannot establish national rankings. |
| Trail use by park | Created a `UNITNAME × TRLUSE` stacked bar visualization | Mixed categories and a nearly invisible Santa Monica Mountains bar require diagnosis; no firm conclusion yet. |
| Trail use labels | Observed `Hike`, `Hiker/Pedestrian`, combined uses, and possible whitespace inconsistencies | Preserve raw values; audit with `repr()`, trim whitespace, and map categories carefully. |
| Trail class | Examined `TRLCLASS` as development class (Class 1–5) | Development class **is not** hiking difficulty. |
| Trail surface | Planned / explored `TRLSURFACE` counts and class-by-surface cross-tabs | Evaluate missingness before using it in ranking. |
| Status filter | Established `df[df['TRLSTATUS'] == 'Existing'].copy()` | Existing means the feature exists, **not** that it is currently open. |
| Park-level summaries | Discussed `segment_count`, hiking-related segment share, and category counts | GIS segmentation and uneven coverage may bias comparisons. |

**Interpretation policy:** The team has a preliminary EDA workflow and at least one trail-use-by-park chart, but **no confirmed nationwide EDA findings** should be claimed from the incomplete data. Do not infer that a park has “the most hiking,” or that its hikes are easier, solely from GIS feature counts.

### 3.4 Route geometry pipeline 🟡

- Downloaded MORA line geometry from the NPS public FeatureServer (204 features) and the NPMap MORA trail overlay (305 features) into `data/raw/`; see `docs/geometry_pipeline.md`.
- Built candidate maps for Nisqually Vista, Naches Peak Loop, and Skyline Loop (`outputs/maps/`). Name matching finds candidates; it does not prove route membership.
- **One of three pilot routes is mapped:** Nisqually Vista is exported to `data/processed/trail_routes.geojson` with status `provisional_open_loop` and `geometry_verified = false`. Its four segments form one connected piece but no closed loop (the nearest open endpoints are about 47 m apart), and the mapped length is 0.74 mi against an official 1.2 mi.
- Naches Peak Loop and Skyline Loop have candidate segments only; no route mapping yet.
- `trails.csv` is now the source of truth for route attributes (see 3.5). `config/route_mappings.json` still carries its own copy of the Nisqually Vista distance, gain, and duration; those duplicate fields should be removed so the mapping only lists which segments make up a route.

### 3.5 Working prototype 🟡

Built on November 13, 2026. Run it with `streamlit run app.py`; rebuild the data with `scripts/fetch_nps_content.py` then `scripts/build_catalog.py`.

- **Catalog:** 10 Mount Rainier hikes in `data/processed/trails.csv`, each tied to an NPS "Things to Do" record: Nisqually Vista, Naches Peak Loop, Silver Falls, Bench and Snow Lakes, Emmons Moraine, Spray Falls, Rampart Ridge, Burroughs Mountain (to First Burroughs), Shriner Peak, and Gobblers Knob. Skyline Trail is not included because the API has no dedicated record for it.
- **Attributes:** distance, elevation gain, and hiking time were read by hand from each NPS page and stored in `config/trail_catalog.json`. Where NPS gives a time range, `estimated_hours` is the midpoint. These values have had one pass by one person and need a second check.
- **Difficulty:** derived by the draft rule in section 6.1. It yields 1 Easy, 7 Moderate, and 2 Hard, so an "Easy" search returns a single trail.
- **Scenery tags:** assigned by judgment from keywords in the NPS descriptions; not yet reviewed.
- **Photos:** 22 records in `trail_photos.csv` from the NPS API (`/thingstodo` and `/places`). A photo is marked `approved` and `public_domain` automatically when its credit starts with "NPS Photo"; 21 qualify and 1 is held as a `candidate`. No person has reviewed each image or its rights. Images load from NPS servers; no local copies are stored.
- **Map:** OpenStreetMap tiles with one marker per trail at the location NPS lists. Only Nisqually Vista has a route line, drawn dashed as provisional. The other nine show a "route not mapped yet" note.
- **Recommender:** `src/parkmatch/recommender.py` filters, scores, and explains as described in section 6.1.
- **Interface:** preference controls, up to three match cards with reasons, a list of excluded trails with reasons, the map with a detail panel and gallery, a grid of all trails, and a park section with entrance fees.
- **Checks:** 12 automated tests pass (difficulty boundaries, filtering, missing values, repeatable ranking, no-match case, and table joins). The filter, card buttons, whole-park view, and map-marker click were exercised by hand in a browser.
- **Known gaps:** the "current conditions" link follows the standard NPS address pattern and has not been opened to confirm it; choosing a trail from the all-trails grid does not scroll back to the map; the API fetch uses the shared `DEMO_KEY` unless `NPS_API_KEY` is set.

### 3.6 Not yet completed ⬜

- Verified geometry for any route, and route lines for the nine hikes that currently show only a marker.
- A second-person check of trail attributes and scenery tags, and a human review of each photo and its rights.
- Local resized photo copies as a fallback for broken remote links.
- Budget input, deployment, and integration with the park-level module.
- Formal usability or relevance evaluation and any multi-park analysis.

## 4. Data Sources and Acquisition Plan

| Data requirement | Preferred source | Planned use | Caveats |
|---|---|---|---|
| Park names, descriptions, coordinates, activities, fees | [NPS API Documentation](https://www.nps.gov/subjects/developer/api-documentation.htm) | Fetch and normalize into `parks.csv` | Requires an API key; fee types and eligibility matter. |
| Complete hike descriptions, distances, timing, scenic features | [Mount Rainier Day Hiking](https://www.nps.gov/mora/planyourvisit/day-hiking-at-mount-rainier.htm) and official trail pages | Manually verify `trails.csv` | Hiking itineraries differ from GIS line segments; leave unavailable fields null. |
| Trail line geometries | [NPS Public Trails Geographic Feature Layer](https://mapservices.nps.gov/arcgis/rest/services/NationalDatasets/NPS_Public_Trails_Geographic/FeatureServer/0?f=pjson) | Query selected `MORA` geometries with `returnGeometry=true` | Validate line-to-route correspondence and coordinate system. |
| Trail descriptions, duration, trailhead point, and photos as structured data | NPS API `/thingstodo` endpoint filtered to `parkCode=mora` (same API and key as the park data) | Draft `trails.csv` rows and `trail_photos.csv` candidate rows by script, then verify by hand | Distance and elevation gain are usually in free text and need manual checking; gives a point, not a route line; not every listed activity is a hike. |
| Secondary GIS reference | [USGS National Digital Trails](https://www.usgs.gov/national-digital-trails/data) | Cross-check where useful | Not guaranteed to provide complete, named hiking itineraries. |
| Zoomable basemap | OpenStreetMap tiles or another approved basemap provider | Load on demand in the map interface | Follow attribution and tile use policies; do not download a whole static park map. |
| Optional park boundary | NPS official polygon boundary layers | Add park outline to map if useful | Not required for the MVP. |
| Trail photos | NPS API `/thingstodo` images (primary; include credit, alt text, and caption); fallback: [Mount Rainier NPS Photos & Multimedia](https://www.nps.gov/mora/learn/photosmultimedia/index.htm), [NPS Gallery](https://npgallery.nps.gov/) | Store image references and rights metadata | Check rights and individual credits; do not assume every web image is reusable. |
| Trail designation context (optional) | [National Trails System](https://www.nps.gov/subjects/nationaltrailssystem/index.htm) | Fill the optional `designation` label, e.g. where a day hike uses a section of the Pacific Crest National Scenic Trail; possible geometry cross-check | Covers long-distance scenic, historic, and recreation trails, not day hikes; no difficulty, duration, or elevation attributes. Not a primary source. |
| Current trail status | Official NPS alerts/current-conditions pages | Link users to authoritative conditions | Do not equate existing GIS status with live accessibility. |

## 5. V1 Data Model: Files, Not a Database Server

The system uses three logical tables and one geometry collection. Stable keys allow a later migration to SQLite or PostgreSQL without changing the core concepts.

### 5.1 `parks.csv` — one row per park

| Field | Type | Description |
|---|---|---|
| `park_code` | string, primary key | NPS code, e.g. `MORA`. |
| `park_name` | string | Official park name. |
| `latitude`, `longitude` | float | Park reference coordinate, not an individual trailhead. |
| `description` | string | Park overview. |
| `official_url` | string | NPS park page. |
| `entrance_fee_note` | string or null | Fee details, rules, and scope if used for budget features. |

### 5.2 `trails.csv` — one row per **verified complete hiking route**

| Field | Type | Description |
|---|---|---|
| `trail_id` | string, primary key | Stable internal identifier in the form `<PARKCODE>_<ROUTE_NAME>`, e.g. `MORA_NISQUALLY_VISTA` (the format the code already uses). |
| `park_code` | string, foreign key | Matches `parks.csv`. |
| `trail_name` | string | User-facing route name. |
| `area` | string | E.g. Paradise or Sunrise. |
| `distance_miles` | float or null | Specify whether the value covers an entire loop, round trip, or one-way route. |
| `elevation_gain_ft` | float or null | Total ascent when reliably available. |
| `estimated_hours` | float or null | Approximate hiking duration, not a guarantee. |
| `difficulty` | Easy / Moderate / Hard / null | Manually verified or consistently derived using documented criteria. |
| `route_type` | Loop / Out-and-back / Point-to-point / null | Complete route structure. |
| `scenery_tags` | delimited string | E.g. `lake|forest`, parsed to a list in code. |
| `source_url` | string | Official route information source. |
| `last_verified` | date | Date source attributes were last checked. |
| `geometry_verified` | boolean | Whether the geometry matches the named hiking route. |
| `designation` | string or null | Optional National Trails System label, e.g. `Pacific Crest National Scenic Trail (section)`. Null for most routes. |
| `nps_duration_text` | string or null | Hiking time as NPS words it, e.g. `2-3 Hours`; shown to users. |
| `latitude`, `longitude` | float or null | Location NPS lists for the hike; used for the map marker. |
| `summary`, `description` | string | Short and longer NPS text for the detail panel. |
| `alert` | string or null | Closure sentences found in the NPS text at fetch time; not a live status. |
| `seasons` | delimited string | Seasons NPS lists for the hike. |
| `geometry_status` | string | `none`, or the route's validation status such as `provisional_open_loop`. |
| `attribute_note` | string or null | Caveat about how the figures were chosen. |

### 5.3 `trail_routes.geojson` — geographical routes

Each GeoJSON Feature should contain a matching `trail_id`, `park_code`, and `LineString` or `MultiLineString` geometry in WGS84 longitude/latitude coordinates. Geometry may be unavailable, but the UI must acknowledge that rather than inventing a route line.

**Critical distinction:** A raw NPS `OBJECTID` identifies a **GIS trail feature**, while the app's `trail_id` identifies a **complete hiker-facing route**. A route may consist of multiple GIS features; several hiking itineraries may share segments.

### 5.4 `trail_photos.csv` — one row per photo

| Field | Description |
|---|---|
| `photo_id` | Unique image identifier. |
| `trail_id` | Route identifier linking to `trails.csv`. |
| `remote_url` | Original image URL from the source. |
| `local_path` | Resized local copy under `assets/photos/<park_code>/<trail_id>/`; used as the fallback when the remote URL breaks. |
| `sort_order` | Display order within the trail's gallery. |
| `is_cover` | Whether this photo is shown on the recommendation card (one per trail). |
| `alt_text` | Text description for screen readers. |
| `caption` | Brief description of what the image shows. |
| `credit` | Photographer or source attribution. |
| `source_url` | Original source page. |
| `license_type` | One of `public_domain`, `cc_by`, `permission`, `unknown`. |
| `license_url` | Link to the license or permission record, if any. |
| `review_status` | One of `candidate`, `approved`, `rejected`. Fetched photos start as `candidate`. |
| `width`, `height` | Pixel size of the stored image. |
| `retrieved_date` | Date the image record was fetched. |
| `lat`, `lon` | Optional photo location, for possible map pins later. |

One route may have multiple photo records, but the app shows **at most three per trail**, and only rows with `review_status = approved` and a `license_type` other than `unknown`. V1 uses NPS-sourced photos only; there is no user-submitted content.

### 5.5 Repository structure (as built)

```text
national_parks_rec/
├── app.py                      # Streamlit prototype
├── requirements.txt
├── config/
│   ├── trail_catalog.json      # curated hikes and hand-read attributes
│   ├── route_candidates.json
│   └── route_mappings.json     # which GIS segments make up a route
├── data/
│   ├── raw/
│   │   ├── nps_api/            # unchanged NPS API responses
│   │   └── *.geojson           # MORA trail segments and overlay
│   └── processed/
│       ├── parks.csv
│       ├── park_photos.csv
│       ├── trails.csv
│       ├── trail_photos.csv
│       └── trail_routes.geojson
├── scripts/                    # fetch and build steps
├── src/parkmatch/
│   ├── catalog.py              # table loading, join checks, difficulty rule
│   ├── recommender.py
│   ├── geometry.py
│   └── arcgis.py, nps_carto.py, candidates.py
├── tests/
├── docs/geometry_pipeline.md
└── trail/                      # national trail-attribute EDA
```

**Data practices:** Never overwrite raw data; normalize field names and distance units in processed data; preserve source references and missing values; enforce stable IDs; check join integrity across CSV and GeoJSON before display.

## 6. Recommendation Logic

### 6.1 V1: Explainable content-based matching

1. Read the structured preferences object from the UI.
2. Apply **hard eligibility constraints** such as an upper hiking-time limit or an explicit difficulty restriction. Missing values should not silently be treated as satisfying a constraint.
3. Score remaining routes on `scenery_match`, `difficulty_match`, and `time_match`, each normalized to 0–1.
4. Use configurable initial weights, for example:

   `match_score = 0.40 * scenery_match + 0.35 * difficulty_match + 0.25 * time_match`

   These are **illustrative, unvalidated weights**, not learned parameters.
5. Return at most three highest-scoring candidates with concrete explanations and score components.
6. If no route qualifies, explain why and allow the user to adjust preferences instead of presenting unsuitable options.

**As implemented in the prototype (draft rules, open to change):**

- **Difficulty label:** Hard is 8 miles or more, or 2,000 ft of gain or more. Easy is 3 miles or less with under 500 ft of gain. Everything else is Moderate. A route missing distance or gain gets no label. This is a project rule, not an NPS rating.
- **Eligibility:** a route is excluded when it is harder than the chosen level, longer than the upper limit of the chosen time range (limits inclusive), or missing a difficulty or duration.
- **`difficulty_match`:** 1.0 at the chosen level, 0.5 one level easier, 0 two levels easier.
- **`time_match`:** 1.0 inside the chosen range, 0.5 one range shorter, 0.25 two ranges shorter.
- **`scenery_match`:** the share of the user's scenery picks the route has. With no picks, scenery is dropped and the other two weights are rescaled.
- **Ties:** broken by `trail_id`, so results are repeatable.

**Park-level expansion:** Starting location and budget belong primarily in the park-selection stage (estimated driving distance, transport assumptions, entrance fees). With Mount Rainier as the only supported park, these should not create artificial differences between trails.

### 6.2 Evaluation plan

- **Correctness:** Test missing attributes, boundary values, no-match outcomes, consistent rankings, and route-to-photo/map joins.
- **Relevance:** Ask a small group of users to rate trail matches for several preference profiles.
- **Baselines:** Compare personalization against a fixed order, random ordering, or a single-feature ranker.
- **Optional ranking metrics:** Precision@3 or NDCG if sufficient labeled preferences are collected.
- **Future learning-to-rank:** Consider only when there is meaningful user feedback or preference data. Neural-network training is not a V1 prerequisite.

## 7. Map, Detail Panel, and Photo Gallery

- Center the initial map on Mount Rainier and display only validated routes for the chosen park.
- Support panning, zooming, clicking or selecting a route, highlighting it, and opening its details by `trail_id`.
- Display trail name, distance, estimated time, difficulty, elevation gain where available, scenery tags, and the official source.
- Include a prominent **Check current NPS conditions** link rather than claiming live access status without verification.
- Display at most three approved, correctly attributed photos per route (the cover image on the recommendation card, the rest in the detail panel); handle missing photos gracefully.
- Draw routes whose geometry is not yet verified with a distinct style (for example a dashed line) and a visible "provisional geometry" note.
- Use GeoPandas/Shapely for geometry preparation and Folium with Streamlit or `streamlit-folium` for the initial UI; consider MapLibre only if requirements justify a more complex frontend.
- Do not render the full nationwide GIS segment network on the first map load.

## 8. Risks, Data Quality, and Limitations

| Risk | Potential impact | Mitigation |
|---|---|---|
| 31,377 GIS features are not 31,377 complete hikes | Incorrect route display and misleading recommendations | Manually match and validate a curated set of complete routes. |
| ArcGIS query intermittently returns code 500 | Retrieval cannot complete reliably | Use object-ID batches, bounded retries, saved checkpoints, and park-scoped queries. |
| Saved dataset is partial and nonrandom | Distorted cross-park EDA | Clearly label partial samples; do not infer national totals. |
| Mixed or missing `TRLUSE` values | Incorrect hiking classification | Preserve original values, document normalization rules, flag unknowns. |
| `TRLCLASS` is not physical difficulty | Mismatched ability recommendations | Use verified full-route distance, ascent, and route descriptions to define difficulty. |
| Geographic `Shape__Length` is not measured in miles | Invalid route distance | Prefer official complete-route distances; use appropriate geodesic/projected length calculations only for validation. |
| `TRLSTATUS='Existing'` is not live openness | Potentially unsafe or inaccurate availability claims | Provide official current-conditions sources; avoid unsupported “open now” language. |
| Image copyright or unstable URLs | Compliance or broken gallery | Track rights, credits, and sources; use fallback states. |
| Incomplete features and unequal GIS mapping coverage | Biased recommendation scores | Document completeness and avoid raw segment counts as a direct measure of hiking quality. |

## 9. Team Roles and Milestones

### 9.1 Suggested ownership

- **Tracy — Trail Discovery & Recommendation:** Curated trail catalog, trail-specific GIS geometries, trail EDA/cleaning, map-data preparation, photos and matching metadata, and trail-level scoring interface.
- **Teammate B — Park-level recommendations:** Park API data, location and budget logic, and a future multi-park selection layer.
- **Teammate C — Frontend and integration:** Streamlit preference form, recommendation cards, map/gallery integration, and deployment.
- **All team members:** Validate source data, agree on product priorities, test the integrated application, and prepare the final demo.

### 9.2 Delivery milestones

| Milestone | Work | Definition of done |
|---|---|---|
| P0 — Data proof | Three complete Mount Rainier routes with details, geometry, and image records | All four datasets join via `trail_id`; each displayed line represents the intended route. |
| P1 — Explorer | Clickable map, route details, photo gallery | Clicking each route loads the correct information and available photos. |
| P2 — Recommender | Structured inputs, filter/score/rank, explanations | Preference changes produce sensible, reproducible top-three results. |
| P3 — Integrated MVP | Expand toward 10–15 routes and connect team modules | Working, presentable end-to-end Streamlit application. |
| P4 — Validation and documentation | Testing, refinement, final explanation | Critical workflows pass and limitations are explicitly disclosed. |

**Status as of November 13, 2026:** P0 is partly met: the four datasets join by `trail_id` for 10 routes, but only one route has a line and it is not verified. P1 and P2 work in the local prototype, with markers standing in for the nine missing route lines. P3 has reached 10 routes but is not integrated with teammates' modules or deployed. P4 has automated tests only.

## 10. Immediate Next Steps

1. Have a second person check each trail's distance, gain, time, and scenery tags in `config/trail_catalog.json` against its NPS page.
2. Review every photo and its credit, and decide what to do with the one held as a candidate.
3. Agree on the difficulty rule as a team, since it currently leaves only one Easy trail.
4. Close the Nisqually Vista loop gap, then map route lines for Naches Peak Loop and the other hikes, in order of how often they are recommended.
5. Open the "current conditions" link to confirm it, and correct it if needed.
6. Get a personal NPS API key and set `NPS_API_KEY`.
7. Hand the prototype to the frontend and park-level owners to agree how the modules connect.
8. Run a small relevance check: a few people rate the top-three results for several preference profiles.

## 11. Decisions Still Open

- Should the V1 landing page lead with **park recommendation → trail recommendation**, or open directly into a **Mount Rainier trail explorer**? Recommended: emphasize the trail explorer in V1 while keeping park-level interfaces modular.
- Should budget actively influence the demo? Only if assumptions are transparent and underlying data are dependable.
- Is the draft difficulty rule in section 6.1 acceptable, or should the Easy thresholds be loosened so more than one trail qualifies? (Routes with missing ascent or time are currently excluded.)
- Which map/tile provider supports the intended deployment and attribution requirements?
- How many of the 10 prototype routes can get a verified route line within the schedule, and is a marker-only display acceptable for the rest?
- Should Skyline Trail be added by hand even though the NPS API has no dedicated record for it?

---

## V1 Success Definition

A user chooses preferences through a fixed set of controls; ParkMatch recommends up to three suitable routes from a curated, verified Mount Rainier trail catalog, explains the matches, and lets the user click each trail on a map to inspect trustworthy route information and photos. The data and code interfaces should allow additional parks to be added without a fundamental redesign.
