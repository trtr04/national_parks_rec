"""Build the first auditable route mapping from the official NPS overlays."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
from typing import Any

import folium
import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parkmatch.geometry import (  # noqa: E402
    as_route_geometry,
    bounds,
    coordinate_at_fraction,
    endpoint_topology,
    geometry_length_miles,
    iter_lines,
)


OVERLAY_INPUT = ROOT / "data" / "raw" / "nps_mora_npmap_overlay.geojson"
CURRENT_INPUT = ROOT / "data" / "raw" / "nps_mora_segments.geojson"
MAPPING_CONFIG = ROOT / "config" / "route_mappings.json"
SEGMENTS_OUTPUT = ROOT / "data" / "processed" / "route_segments.csv"
ROUTES_OUTPUT = ROOT / "data" / "processed" / "npmap_nisqually_route.geojson"
VALIDATION_OUTPUT = ROOT / "data" / "processed" / "route_validation.json"
MAP_OUTPUT = ROOT / "outputs" / "maps" / "mora_nisqually_route_mapping.html"
FIGURE_OUTPUT = ROOT / "outputs" / "maps" / "mora_nisqually_route_mapping.png"


def build_validation_figure(
    unique_features: list[dict[str, Any]],
    segment_config: dict[int, dict[str, Any]],
    gap_start: list[float],
    gap_end: list[float],
    gap_meters: float,
) -> None:
    """Draw source segments and make the unresolved gap visually explicit."""

    figure, axis = plt.subplots(figsize=(10, 8))
    segment_color = "#2166ac"
    for feature in unique_features:
        cartodb_id = int(feature["properties"]["cartodb_id"])
        segment = segment_config[cartodb_id]
        for line in iter_lines(feature["geometry"]):
            axis.plot(
                [point[0] for point in line],
                [point[1] for point in line],
                color=segment_color,
                linewidth=4,
                solid_capstyle="round",
            )
        lon, lat = coordinate_at_fraction(feature["geometry"])
        current_id = segment["current_feature_objectid"]
        current_label = "" if current_id is None else f"\ncurrent OID {current_id}"
        axis.annotate(
            f"NPMap OID {segment['source_objectid']}{current_label}",
            (lon, lat),
            fontsize=8,
            fontweight="bold",
            bbox={
                "boxstyle": "round,pad=0.2",
                "facecolor": "white",
                "edgecolor": segment_color,
                "alpha": 0.9,
            },
        )

    axis.plot(
        [gap_start[0], gap_end[0]],
        [gap_start[1], gap_end[1]],
        color="#111111",
        linewidth=2,
        linestyle="--",
        label=f"Unresolved source gap ({gap_meters:.1f} m)",
    )
    axis.scatter(
        [gap_start[0], gap_end[0]],
        [gap_start[1], gap_end[1]],
        color="#111111",
        s=30,
        zorder=5,
    )
    axis.plot(
        [],
        [],
        color=segment_color,
        linewidth=4,
        label="Mapped source segment (unordered)",
    )
    axis.set_title(
        "Nisqually Vista route-to-segment mapping\n"
        "No traversal order; nearest open-endpoint gap is shown, not filled"
    )
    axis.set_xlabel("Longitude")
    axis.set_ylabel("Latitude")
    axis.xaxis.set_major_formatter(FormatStrFormatter("%.5f"))
    axis.yaxis.set_major_formatter(FormatStrFormatter("%.5f"))
    axis.set_aspect("equal", adjustable="box")
    axis.grid(True, color="#e5e5e5", linewidth=0.5)
    axis.legend(loc="best")
    figure.tight_layout()
    FIGURE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE_OUTPUT, dpi=180)
    plt.close(figure)


def main() -> None:
    overlay = json.loads(OVERLAY_INPUT.read_text(encoding="utf-8"))
    current = json.loads(CURRENT_INPUT.read_text(encoding="utf-8"))
    config = json.loads(MAPPING_CONFIG.read_text(encoding="utf-8"))
    route = config["routes"][0]

    by_cartodb_id = {
        int(feature["properties"]["cartodb_id"]): feature
        for feature in overlay["features"]
    }
    segment_config = {
        int(segment["cartodb_id"]): segment for segment in route["segments"]
    }
    unique_features = [
        by_cartodb_id[int(segment["cartodb_id"])] for segment in route["segments"]
    ]

    for segment, feature in zip(route["segments"], unique_features):
        properties = feature["properties"]
        if properties.get("geometry_id") != route["geometry_id"]:
            raise RuntimeError("Configured segment has an unexpected geometry_id")
        if properties.get("name") != route["display_name"]:
            raise RuntimeError("Configured segment has an unexpected trail name")
        if str(properties.get("object_id")) != segment["source_objectid"]:
            raise RuntimeError("Configured source OBJECTID does not match overlay")

    mapping_rows: list[dict[str, Any]] = []
    for segment, feature in zip(route["segments"], unique_features):
        cartodb_id = int(segment["cartodb_id"])
        segment_length = geometry_length_miles(feature["geometry"])
        mapping_rows.append(
            {
                "trail_id": route["trail_id"],
                "source": route["geometry_source"],
                "source_cartodb_id": cartodb_id,
                "source_objectid": segment["source_objectid"],
                "source_geometry_id": route["geometry_id"],
                "current_feature_objectid": (
                    ""
                    if segment["current_feature_objectid"] is None
                    else segment["current_feature_objectid"]
                ),
                "segment_geometry_miles": round(segment_length, 4),
                "validation_status": route["validation_status"],
            }
        )

    route_geometry = as_route_geometry(unique_features)
    unique_geometry_length = geometry_length_miles(route_geometry)
    official_distance = float(route["official_distance_miles"])
    topology = endpoint_topology(unique_features, tolerance_meters=15.0)
    nearest_pair = topology["nearest_open_endpoint_pair"]
    if nearest_pair is None:
        raise RuntimeError("Expected at least two open endpoints for diagnostics")

    current_by_id = {
        int(feature["properties"]["OBJECTID"]): feature
        for feature in current["features"]
    }
    current_coverage = sum(
        1
        for segment in route["segments"]
        if segment["current_feature_objectid"] in current_by_id
    )

    SEGMENTS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with SEGMENTS_OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(mapping_rows[0]))
        writer.writeheader()
        writer.writerows(mapping_rows)

    route_feature = {
        "type": "Feature",
        "properties": {
            "trail_id": route["trail_id"],
            "trail_name": route["display_name"],
            "route_type": route["route_type"],
            "official_distance_miles": official_distance,
            "official_elevation_gain_ft": route["official_elevation_gain_ft"],
            "official_duration_minutes": route["official_duration_minutes"],
            "unique_geometry_miles": round(unique_geometry_length, 4),
            "geometry_verified": False,
            "validation_status": route["validation_status"],
            "official_source_url": route["official_source_url"],
            "geometry_source": route["geometry_source"],
            "geometry_source_url": route["geometry_source_url"],
            "source_geometry_id": route["geometry_id"],
        },
        "geometry": route_geometry,
    }
    ROUTES_OUTPUT.write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": [route_feature]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    validation = {
        "trail_id": route["trail_id"],
        "validation_status": route["validation_status"],
        "geometry_verified": False,
        "official_distance_miles": official_distance,
        "unique_geometry_miles": round(unique_geometry_length, 4),
        "topology": topology,
        "npmap_segments_used": len(unique_features),
        "current_feature_segments_available": current_coverage,
        "validation_note": route["validation_note"],
        "official_source_url": route["official_source_url"],
        "geometry_source_url": route["geometry_source_url"],
    }
    VALIDATION_OUTPUT.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    min_lon, min_lat, max_lon, max_lat = bounds(unique_features)
    route_map = folium.Map(
        location=[(min_lat + max_lat) / 2, (min_lon + max_lon) / 2],
        zoom_start=16,
        tiles="OpenStreetMap",
        control_scale=True,
    )
    folium.GeoJson(
        current,
        name="Current MORA FeatureServer segments",
        style_function=lambda _: {
            "color": "#999999",
            "weight": 1,
            "opacity": 0.25,
        },
        tooltip=folium.GeoJsonTooltip(fields=["OBJECTID", "TRLNAME"]),
    ).add_to(route_map)

    segment_color = "#2166ac"
    for feature in unique_features:
        cartodb_id = int(feature["properties"]["cartodb_id"])
        segment = segment_config[cartodb_id]
        source_objectid = segment["source_objectid"]
        folium.GeoJson(
            feature,
            name=f"NPMap segment {source_objectid}",
            style_function=lambda _, line_color=segment_color: {
                "color": line_color,
                "weight": 6,
                "opacity": 0.9,
            },
            tooltip=(
                f"NPMap OBJECTID {source_objectid} | "
                f"cartodb_id {cartodb_id}"
            ),
        ).add_to(route_map)
        lon, lat = coordinate_at_fraction(feature["geometry"])
        folium.Marker(
            [lat, lon],
            tooltip=f"NPMap OBJECTID {source_objectid}",
            icon=folium.DivIcon(
                html=(
                    "<div style='font-size:11px;font-weight:bold;background:white;"
                    "border:1px solid #333;padding:2px;white-space:nowrap;'>"
                    f"{source_objectid}</div>"
                )
            ),
        ).add_to(route_map)

    folium.LayerControl(collapsed=False).add_to(route_map)
    route_map.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])
    MAP_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    route_map.save(MAP_OUTPUT)
    build_validation_figure(
        unique_features,
        segment_config,
        nearest_pair["left"],
        nearest_pair["right"],
        nearest_pair["gap_meters"],
    )

    print(f"Saved route-to-segment mapping to {SEGMENTS_OUTPUT}")
    print(f"Saved route geometry to {ROUTES_OUTPUT}")
    print(f"Saved validation report to {VALIDATION_OUTPUT}")
    print(f"Saved route map to {MAP_OUTPUT}")
    print(f"Saved validation figure to {FIGURE_OUTPUT}")
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    main()

