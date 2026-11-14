"""Build an inspectable Folium map of candidate route segments."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any

import folium


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parkmatch.candidates import object_id, select_by_names  # noqa: E402
from parkmatch.geometry import (  # noqa: E402
    bounds,
    coordinate_at_fraction,
    endpoint_gap_meters,
    geometry_length_miles,
    is_closed,
)


DEFAULT_INPUT = ROOT / "data" / "raw" / "nps_mora_segments.geojson"
DEFAULT_CONFIG = ROOT / "config" / "route_candidates.json"
DEFAULT_MAP = ROOT / "outputs" / "maps" / "mora_route_candidates.html"
DEFAULT_SUMMARY = ROOT / "outputs" / "maps" / "mora_candidate_segments.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--map-output", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args()


def label_segment(
    layer: folium.FeatureGroup, feature: dict[str, Any], color: str
) -> None:
    properties = feature["properties"]
    oid = object_id(feature)
    name = properties.get("TRLNAME") or "Unnamed"
    length_miles = geometry_length_miles(feature["geometry"])
    gap = endpoint_gap_meters(feature["geometry"])
    gap_label = "multipart" if gap is None else f"{gap:.1f} m"

    folium.GeoJson(
        feature,
        style_function=lambda _, line_color=color: {
            "color": line_color,
            "weight": 6,
            "opacity": 0.9,
        },
        tooltip=(
            f"OBJECTID {oid} | {name} | "
            f"geometry {length_miles:.3f} mi | endpoint gap {gap_label}"
        ),
        popup=folium.Popup(
            f"<b>{name}</b><br>OBJECTID: {oid}<br>"
            f"Geometry length: {length_miles:.3f} mi<br>"
            f"Closed within 15 m: {is_closed(feature['geometry'])}",
            max_width=320,
        ),
    ).add_to(layer)

    lon, lat = coordinate_at_fraction(feature["geometry"])
    folium.Marker(
        [lat, lon],
        icon=folium.DivIcon(
            html=(
                "<div style='font-size:10px;font-weight:bold;color:#111;"
                "background:white;border:1px solid #555;padding:1px 3px;"
                "white-space:nowrap;'>"
                f"{oid}</div>"
            )
        ),
        tooltip=f"OBJECTID {oid}",
    ).add_to(layer)


def main() -> None:
    args = parse_args()
    geojson = json.loads(args.input.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))
    all_features = geojson["features"]

    selected_by_route: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    selected_ids: set[int] = set()
    for route in config["routes"]:
        selected = select_by_names(all_features, route["candidate_names"])
        selected.sort(key=object_id)
        selected_by_route.append((route, selected))
        selected_ids.update(object_id(feature) for feature in selected)

    candidate_features = [
        feature for feature in all_features if object_id(feature) in selected_ids
    ]
    if not candidate_features:
        raise RuntimeError("No candidate features matched the configured names")

    min_lon, min_lat, max_lon, max_lat = bounds(candidate_features)
    route_map = folium.Map(
        location=[(min_lat + max_lat) / 2, (min_lon + max_lon) / 2],
        zoom_start=11,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    background = folium.FeatureGroup(name="All MORA segments", show=False)
    folium.GeoJson(
        geojson,
        style_function=lambda _: {
            "color": "#888888",
            "weight": 1,
            "opacity": 0.25,
        },
        tooltip=folium.GeoJsonTooltip(fields=["OBJECTID", "TRLNAME"]),
    ).add_to(background)
    background.add_to(route_map)

    rows: list[dict[str, Any]] = []
    for route, features in selected_by_route:
        layer = folium.FeatureGroup(
            name=f"{route['display_name']} ({len(features)} candidates)",
            show=True,
        )
        for feature in features:
            label_segment(layer, feature, route["color"])
            gap = endpoint_gap_meters(feature["geometry"])
            rows.append(
                {
                    "trail_id": route["trail_id"],
                    "route_name": route["display_name"],
                    "objectid": object_id(feature),
                    "trail_name": feature["properties"].get("TRLNAME") or "",
                    "geometry_type": feature["geometry"]["type"],
                    "geometry_length_miles": round(
                        geometry_length_miles(feature["geometry"]), 4
                    ),
                    "endpoint_gap_meters": (
                        "" if gap is None else round(gap, 1)
                    ),
                    "closed_within_15m": is_closed(feature["geometry"]),
                }
            )
        layer.add_to(route_map)

    folium.LayerControl(collapsed=False).add_to(route_map)
    route_map.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])

    args.map_output.parent.mkdir(parents=True, exist_ok=True)
    route_map.save(args.map_output)

    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    with args.summary_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved candidate map to {args.map_output}")
    print(f"Saved {len(rows)} candidate rows to {args.summary_output}")
    for route, features in selected_by_route:
        ids = [object_id(feature) for feature in features]
        print(f"{route['display_name']}: {ids}")


if __name__ == "__main__":
    main()

