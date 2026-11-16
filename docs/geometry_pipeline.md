# Mount Rainier route geometry workflow

This pipeline deliberately separates source retrieval, candidate discovery,
route mapping, and validation.

## Reproduce the source data

```bash
python3 scripts/fetch_mora_geometry.py
python3 scripts/fetch_mora_reference_overlay.py
```

The first command downloads the current NPS public FeatureServer records for
`UNITCODE='MORA'` in WGS84. The second downloads the MORA trail overlay used by
official NPS NPMap pages. Raw downloads are retained unchanged.

## Inspect candidates

```bash
python3 scripts/build_candidate_map.py
MPLCONFIGDIR=/tmp/parkmatch_mpl python3 scripts/build_static_candidate_maps.py
```

The interactive map labels the current FeatureServer candidates by `OBJECTID`.
The static maps show name-matched segments in color and nearby NPS segments in
gray. Name matching discovers candidates; it does not prove route membership.

## Build the first route mapping

```bash
python3 scripts/build_first_route_mapping.py
```

The route-to-segment membership is configured in `config/route_mappings.json`.
It is an unordered set: no walking sequence, forward/reverse direction, or
outbound/return duplication is stored. The build checks the source name,
`geometry_id`, source object ID, and endpoint topology before exporting data.

The first Nisqually Vista mapping is intentionally marked
`provisional_open_loop`, not verified. The current FeatureServer contains only
one of the four same-`geometry_id` pieces visible in the official NPMap overlay.
Automatic endpoint topology finds one connected component, but it does not find
a closed cycle. The nearest pair of open loop endpoints is roughly 47 meters
apart. No straight-line connector or manual traversal order is invented.


## Route lines for the app (Washington State Trails Database)

```bash
python3 scripts/fetch_wa_trails.py
python3 scripts/build_routes.py
python3 scripts/build_catalog.py
```

The app's `data/processed/trail_routes.geojson` is now built from the
Washington State Trails Database v2.0 (Recreation and Conservation Office),
which has named lines for every hike in the catalog. Each hike's segments are
listed by `OBJECTID` under `route` in `config/trail_catalog.json`. They were
chosen by hand from trail names and shared endpoints. A segment can carry a
clip box to keep only part of a longer trail.

`build_routes.py` joins the listed segments as an unordered MultiLineString.
It does not add connectors or store a walking order. It writes
`data/processed/route_checks.csv`, which reports the line length, the walked
length (doubled for out-and-back routes), the official distance, and how many
connected pieces the line has.

Every route is written with `validation_status = provisional_name_match` and
`geometry_verified = false`. Known differences as of the first build:

- Silver Falls has a gap through the Ohanapecosh Campground.
- Gobblers Knob covers only the trail section, not the Westside Road walk.
- Emmons Moraine is longer than the official distance (3.8 vs 3.0 miles walked).
- The `segment_length_mi` field in the source is about 46% too long at this
  latitude, which is what a Web Mercator measurement would give. Lengths here
  are measured on the sphere from the coordinates instead.

The earlier NPMap-based Nisqually Vista mapping is kept for reference. Its
script now writes `data/processed/npmap_nisqually_route.geojson`.
