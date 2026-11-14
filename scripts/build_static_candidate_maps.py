"""Create static candidate maps for visual review and documentation."""

from __future__ import annotations

import json
from math import cos, radians
from pathlib import Path
import sys
from typing import Any

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parkmatch.candidates import object_id, select_by_names  # noqa: E402
from parkmatch.geometry import (  # noqa: E402
    bounds,
    coordinate_at_fraction,
    haversine_meters,
    iter_lines,
)


INPUT = ROOT / "data" / "raw" / "nps_mora_segments.geojson"
CONFIG = ROOT / "config" / "route_candidates.json"
OUTPUT_DIR = ROOT / "outputs" / "maps"


def sampled_coordinates(feature: dict[str, Any], max_points: int = 80) -> list[list[float]]:
    coordinates = [point for line in iter_lines(feature["geometry"]) for point in line]
    step = max(1, len(coordinates) // max_points)
    return coordinates[::step]


def near_candidates(
    feature: dict[str, Any],
    candidate_points: list[list[float]],
    radius_meters: float,
) -> bool:
    points = sampled_coordinates(feature)
    return any(
        haversine_meters(point, candidate) <= radius_meters
        for point in points
        for candidate in candidate_points
    )


def project(point: list[float], center_lat: float) -> tuple[float, float]:
    lon, lat = float(point[0]), float(point[1])
    return lon * cos(radians(center_lat)), lat


def plot_route(
    all_features: list[dict[str, Any]], route: dict[str, Any]
) -> Path:
    candidates = select_by_names(all_features, route["candidate_names"])
    candidate_ids = {object_id(feature) for feature in candidates}
    candidate_points = [
        point for feature in candidates for point in sampled_coordinates(feature)
    ]
    nearby = [
        feature
        for feature in all_features
        if near_candidates(
            feature, candidate_points, route["neighborhood_radius_meters"]
        )
    ]

    candidate_min_lon, candidate_min_lat, candidate_max_lon, candidate_max_lat = bounds(
        candidates
    )
    center_lat = (candidate_min_lat + candidate_max_lat) / 2
    figure, axis = plt.subplots(figsize=(11, 9))

    for feature in nearby:
        oid = object_id(feature)
        is_candidate = oid in candidate_ids
        for line in iter_lines(feature["geometry"]):
            projected = [project(point, center_lat) for point in line]
            axis.plot(
                [point[0] for point in projected],
                [point[1] for point in projected],
                color=route["color"] if is_candidate else "#9e9e9e",
                linewidth=3.2 if is_candidate else 1.0,
                alpha=0.95 if is_candidate else 0.55,
                zorder=3 if is_candidate else 1,
            )

        lon, lat = coordinate_at_fraction(feature["geometry"])
        x, y = project([lon, lat], center_lat)
        name = feature["properties"].get("TRLNAME") or "Unnamed"
        label = f"{oid}\n{name}" if is_candidate else f"{oid}"
        axis.annotate(
            label,
            (x, y),
            fontsize=7 if is_candidate else 6,
            fontweight="bold" if is_candidate else "normal",
            color="#111111" if is_candidate else "#555555",
            bbox={
                "boxstyle": "round,pad=0.15",
                "facecolor": "white",
                "edgecolor": route["color"] if is_candidate else "none",
                "alpha": 0.8,
            },
            zorder=4,
        )

    axis.set_title(
        f"{route['display_name']} candidate segments\n"
        f"colored = name match; gray = nearby NPS segments",
        fontsize=13,
    )
    axis.set_aspect("equal", adjustable="box")
    radius_meters = float(route["neighborhood_radius_meters"])
    latitude_padding = radius_meters / 111_320
    longitude_padding = radius_meters / (111_320 * cos(radians(center_lat)))
    axis.set_xlim(
        (candidate_min_lon - longitude_padding) * cos(radians(center_lat)),
        (candidate_max_lon + longitude_padding) * cos(radians(center_lat)),
    )
    axis.set_ylim(
        candidate_min_lat - latitude_padding,
        candidate_max_lat + latitude_padding,
    )
    axis.set_xlabel("Longitude (scaled for display)")
    axis.set_ylabel("Latitude")
    axis.grid(True, color="#e8e8e8", linewidth=0.5)
    figure.tight_layout()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / f"{route['trail_id'].lower()}_candidates.png"
    figure.savefig(output, dpi=180)
    plt.close(figure)
    print(
        f"Saved {output} ({len(candidates)} named candidates, "
        f"{len(nearby)} nearby segments)"
    )
    return output


def main() -> None:
    all_features = json.loads(INPUT.read_text(encoding="utf-8"))["features"]
    routes = json.loads(CONFIG.read_text(encoding="utf-8"))["routes"]
    for route in routes:
        plot_route(all_features, route)


if __name__ == "__main__":
    main()

