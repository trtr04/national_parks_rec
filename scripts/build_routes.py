"""Build one provisional route line per curated hike.

Each hike in config/trail_catalog.json lists the Washington State Trails
Database segments (by OBJECTID) that make up its route. This script joins
them as an unordered MultiLineString, reports how well they connect and how
their length compares with the official distance, and writes
data/processed/trail_routes.geojson plus data/processed/route_checks.csv.

No connector is invented and no walking order is stored. Every route is
written as provisional: a person still has to compare it with the official
NPS map before geometry_verified can be set.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parkmatch.geometry import (  # noqa: E402
    clip_lines_to_bbox,
    endpoint_topology,
    geometry_length_miles,
    iter_lines,
)


CONFIG = ROOT / "config" / "trail_catalog.json"
ROUTES_OUTPUT = ROOT / "data" / "processed" / "trail_routes.geojson"
CHECKS_OUTPUT = ROOT / "data" / "processed" / "route_checks.csv"
STATUS = "provisional_name_match"
CONNECT_TOLERANCE_METERS = 25.0
# How many times the drawn line is walked to cover the official distance.
WALK_MULTIPLIER = {"Loop": 1, "Out-and-back": 2}


def main() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    source = config["route_source"]
    raw = json.loads((ROOT / source["raw_file"]).read_text(encoding="utf-8"))
    segments = {f["properties"]["OBJECTID"]: f for f in raw["features"]}

    features: list[dict] = []
    checks: list[dict] = []
    for entry in config["trails"]:
        spec = entry.get("route")
        if not spec:
            continue
        parts: list[dict] = []
        object_ids: list[int] = []
        for item in spec["segments"]:
            object_id = item["objectid"] if isinstance(item, dict) else item
            if object_id not in segments:
                raise SystemExit(
                    f"{entry['trail_id']}: OBJECTID {object_id} is not in the raw file"
                )
            geometry = segments[object_id]["geometry"]
            if isinstance(item, dict) and item.get("clip"):
                lines = clip_lines_to_bbox(geometry, item["clip"])
                if not lines:
                    raise SystemExit(
                        f"{entry['trail_id']}: clip removed all of OBJECTID {object_id}"
                    )
            else:
                lines = [list(line) for line in iter_lines(geometry)]
            object_ids.append(object_id)
            parts.append(
                {"geometry": {"type": "MultiLineString", "coordinates": lines}}
            )

        geometry = {
            "type": "MultiLineString",
            "coordinates": [
                line for part in parts for line in part["geometry"]["coordinates"]
            ],
        }
        topology = endpoint_topology(parts, tolerance_meters=CONNECT_TOLERANCE_METERS)
        line_miles = geometry_length_miles(geometry)
        multiplier = WALK_MULTIPLIER.get(entry["route_type"])
        walked_miles = line_miles * multiplier if multiplier else None
        ratio = (
            walked_miles / entry["distance_miles"]
            if walked_miles and entry["distance_miles"]
            else None
        )

        features.append(
            {
                "type": "Feature",
                "properties": {
                    "trail_id": entry["trail_id"],
                    "park_code": config["park_code"],
                    "trail_name": entry["trail_name"],
                    "validation_status": STATUS,
                    "geometry_verified": False,
                    "geometry_source": source["name"],
                    "geometry_source_url": source["url"],
                    "source_objectids": object_ids,
                    "line_miles": round(line_miles, 2),
                    "official_distance_miles": entry["distance_miles"],
                    "connected_component_count": topology[
                        "connected_component_count"
                    ],
                    "route_note": spec.get("note"),
                },
                "geometry": geometry,
            }
        )
        checks.append(
            {
                "trail_id": entry["trail_id"],
                "route_type": entry["route_type"],
                "segments": len(object_ids),
                "line_miles": round(line_miles, 2),
                "walked_miles": round(walked_miles, 2) if walked_miles else "",
                "official_distance_miles": entry["distance_miles"],
                "walked_to_official_ratio": round(ratio, 2) if ratio else "",
                "connected_components": topology["connected_component_count"],
                "open_endpoints": topology["open_endpoint_count"],
                "validation_status": STATUS,
            }
        )

    ROUTES_OUTPUT.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )
    with CHECKS_OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(checks[0].keys()))
        writer.writeheader()
        writer.writerows(checks)

    print(f"Wrote {len(features)} routes to {ROUTES_OUTPUT.relative_to(ROOT)}")
    for row in checks:
        print(
            f"  {row['trail_id']:26} line {row['line_miles']:5} mi | "
            f"walked {row['walked_miles'] or '-':>5} vs official "
            f"{row['official_distance_miles']:>4} | pieces "
            f"{row['connected_components']}"
        )


if __name__ == "__main__":
    main()
