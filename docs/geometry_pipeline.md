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

