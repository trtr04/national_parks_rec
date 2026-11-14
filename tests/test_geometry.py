from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parkmatch.geometry import (  # noqa: E402
    endpoint_topology,
    endpoint_gap_meters,
    geometry_length_meters,
    is_closed,
)


def test_closed_line_is_detected() -> None:
    geometry = {
        "type": "LineString",
        "coordinates": [
            [-121.7, 46.8],
            [-121.699, 46.8],
            [-121.7, 46.8],
        ],
    }
    assert is_closed(geometry)
    assert endpoint_gap_meters(geometry) == 0
    assert geometry_length_meters(geometry) > 0


def test_open_line_is_not_closed() -> None:
    geometry = {
        "type": "LineString",
        "coordinates": [[-121.7, 46.8], [-121.69, 46.8]],
    }
    assert not is_closed(geometry)
    assert endpoint_gap_meters(geometry) > 100


def test_multipart_endpoint_gap_is_not_assumed() -> None:
    geometry = {
        "type": "MultiLineString",
        "coordinates": [
            [[-121.7, 46.8], [-121.69, 46.8]],
            [[-121.69, 46.8], [-121.68, 46.8]],
        ],
    }
    assert endpoint_gap_meters(geometry) is None
    assert not is_closed(geometry)


def test_endpoint_topology_detects_cycle_without_route_order() -> None:
    features = [
        {
            "geometry": {
                "type": "LineString",
                "coordinates": [[-121.7, 46.8], [-121.699, 46.8]],
            }
        },
        {
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [-121.699, 46.8],
                    [-121.699, 46.801],
                    [-121.7, 46.8],
                ],
            }
        },
    ]
    topology = endpoint_topology(features)
    assert topology["connected_component_count"] == 1
    assert topology["open_endpoint_count"] == 0
    assert topology["cycle_rank"] == 1

