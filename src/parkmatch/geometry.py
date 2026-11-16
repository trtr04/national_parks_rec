"""Dependency-light GeoJSON geometry inspection utilities."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from math import asin, cos, radians, sin, sqrt
from typing import Any


Coordinate = Sequence[float]
EARTH_RADIUS_METERS = 6_371_008.8
METERS_PER_MILE = 1_609.344


def iter_lines(geometry: dict[str, Any]) -> Iterator[list[Coordinate]]:
    """Yield coordinate arrays from a LineString or MultiLineString."""

    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "LineString":
        yield coordinates
    elif geometry_type == "MultiLineString":
        yield from coordinates
    else:
        raise ValueError(f"Unsupported geometry type: {geometry_type!r}")


def haversine_meters(a: Coordinate, b: Coordinate) -> float:
    """Return geodesic distance between two longitude/latitude coordinates."""

    lon1, lat1 = radians(float(a[0])), radians(float(a[1]))
    lon2, lat2 = radians(float(b[0])), radians(float(b[1]))
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * asin(sqrt(value))


def line_length_meters(line: Sequence[Coordinate]) -> float:
    return sum(haversine_meters(a, b) for a, b in zip(line, line[1:]))


def geometry_length_meters(geometry: dict[str, Any]) -> float:
    return sum(line_length_meters(line) for line in iter_lines(geometry))


def geometry_length_miles(geometry: dict[str, Any]) -> float:
    return geometry_length_meters(geometry) / METERS_PER_MILE


def endpoint_gap_meters(geometry: dict[str, Any]) -> float | None:
    """Return first-to-last endpoint gap for a single LineString.

    ``None`` is returned for multipart geometry because a route order is
    required before its overall endpoint gap has a meaningful interpretation.
    """

    lines = list(iter_lines(geometry))
    if len(lines) != 1 or len(lines[0]) < 2:
        return None
    return haversine_meters(lines[0][0], lines[0][-1])


def is_closed(geometry: dict[str, Any], tolerance_meters: float = 15.0) -> bool:
    gap = endpoint_gap_meters(geometry)
    return gap is not None and gap <= tolerance_meters


def bounds(features: Iterable[dict[str, Any]]) -> tuple[float, float, float, float]:
    """Return min longitude, min latitude, max longitude, max latitude."""

    longitudes: list[float] = []
    latitudes: list[float] = []
    for feature in features:
        for line in iter_lines(feature["geometry"]):
            for coordinate in line:
                longitudes.append(float(coordinate[0]))
                latitudes.append(float(coordinate[1]))
    if not longitudes:
        raise ValueError("Cannot calculate bounds for an empty feature set")
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def coordinate_at_fraction(
    geometry: dict[str, Any], fraction: float = 0.5
) -> tuple[float, float]:
    """Return a point approximately ``fraction`` of the way along a geometry."""

    if not 0 <= fraction <= 1:
        raise ValueError("fraction must be between 0 and 1")

    lines = list(iter_lines(geometry))
    segments: list[tuple[Coordinate, Coordinate, float]] = []
    total = 0.0
    for line in lines:
        for start, end in zip(line, line[1:]):
            length = haversine_meters(start, end)
            segments.append((start, end, length))
            total += length

    if not segments:
        first = lines[0][0]
        return float(first[0]), float(first[1])

    target = total * fraction
    covered = 0.0
    for start, end, length in segments:
        if covered + length >= target:
            ratio = 0.0 if length == 0 else (target - covered) / length
            lon = float(start[0]) + (float(end[0]) - float(start[0])) * ratio
            lat = float(start[1]) + (float(end[1]) - float(start[1])) * ratio
            return lon, lat
        covered += length

    last = segments[-1][1]
    return float(last[0]), float(last[1])


def as_route_geometry(features: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Preserve one line or combine several source lines as a MultiLineString.

    This does not silently join endpoints. A later, explicitly verified route
    ordering step may turn connected parts into a LineString.
    """

    lines: list[list[Coordinate]] = []
    for feature in features:
        lines.extend(iter_lines(feature["geometry"]))
    if len(lines) == 1:
        return {"type": "LineString", "coordinates": lines[0]}
    return {"type": "MultiLineString", "coordinates": lines}


def endpoint_topology(
    features: Sequence[dict[str, Any]], tolerance_meters: float = 15.0
) -> dict[str, Any]:
    """Analyze line connectivity without imposing a traversal order.

    Endpoints within ``tolerance_meters`` are treated as the same graph node.
    The result reports connected components, open endpoints, and cycle rank.
    A lollipop route normally has one open endpoint and one cycle.
    """

    edges: list[tuple[int, Coordinate, Coordinate]] = []
    for feature_index, feature in enumerate(features):
        for line in iter_lines(feature["geometry"]):
            if len(line) >= 2:
                edges.append((feature_index, line[0], line[-1]))

    endpoints: list[Coordinate] = []
    for _, start, end in edges:
        endpoints.extend([start, end])

    parent = list(range(len(endpoints)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left in range(len(endpoints)):
        for right in range(left + 1, len(endpoints)):
            if haversine_meters(endpoints[left], endpoints[right]) <= tolerance_meters:
                union(left, right)

    root_to_node: dict[int, int] = {}
    endpoint_nodes: list[int] = []
    for index in range(len(endpoints)):
        root = find(index)
        root_to_node.setdefault(root, len(root_to_node))
        endpoint_nodes.append(root_to_node[root])

    graph_edges: list[tuple[int, int]] = []
    degrees = {node: 0 for node in root_to_node.values()}
    node_coordinates: dict[int, list[Coordinate]] = {
        node: [] for node in root_to_node.values()
    }
    for endpoint_index, node in enumerate(endpoint_nodes):
        node_coordinates[node].append(endpoints[endpoint_index])
    for edge_index in range(len(edges)):
        start_node = endpoint_nodes[edge_index * 2]
        end_node = endpoint_nodes[edge_index * 2 + 1]
        graph_edges.append((start_node, end_node))
        degrees[start_node] += 1
        degrees[end_node] += 1

    adjacency = {node: set() for node in degrees}
    for start_node, end_node in graph_edges:
        adjacency[start_node].add(end_node)
        adjacency[end_node].add(start_node)

    visited: set[int] = set()
    component_count = 0
    for node in adjacency:
        if node in visited:
            continue
        component_count += 1
        stack = [node]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            stack.extend(adjacency[current] - visited)

    representative_coordinates = {
        node: [
            sum(float(point[0]) for point in points) / len(points),
            sum(float(point[1]) for point in points) / len(points),
        ]
        for node, points in node_coordinates.items()
    }
    open_nodes = [node for node, degree in degrees.items() if degree == 1]
    open_endpoints = [representative_coordinates[node] for node in open_nodes]
    open_endpoint_pairs = []
    for left in range(len(open_endpoints)):
        for right in range(left + 1, len(open_endpoints)):
            open_endpoint_pairs.append(
                {
                    "left": open_endpoints[left],
                    "right": open_endpoints[right],
                    "gap_meters": haversine_meters(
                        open_endpoints[left], open_endpoints[right]
                    ),
                }
            )
    open_endpoint_pairs.sort(key=lambda item: item["gap_meters"])

    cycle_rank = len(graph_edges) - len(degrees) + component_count
    return {
        "tolerance_meters": tolerance_meters,
        "edge_count": len(graph_edges),
        "node_count": len(degrees),
        "connected_component_count": component_count,
        "open_endpoint_count": len(open_endpoints),
        "open_endpoints": open_endpoints,
        "cycle_rank": cycle_rank,
        "nearest_open_endpoint_pair": (
            open_endpoint_pairs[0] if open_endpoint_pairs else None
        ),
    }



def clip_lines_to_bbox(
    geometry: dict[str, Any], bbox: Sequence[float]
) -> list[list[Coordinate]]:
    """Keep the runs of vertices that fall inside ``bbox``.

    ``bbox`` is west, south, east, north. A line that leaves and re-enters
    the box is split into separate runs. No vertices are added at the box
    edge, so each kept run ends at the last source vertex inside the box.
    """

    west, south, east, north = bbox
    kept: list[list[Coordinate]] = []
    for line in iter_lines(geometry):
        run: list[Coordinate] = []
        for coordinate in line:
            inside = (
                west <= float(coordinate[0]) <= east
                and south <= float(coordinate[1]) <= north
            )
            if inside:
                run.append(coordinate)
            else:
                if len(run) >= 2:
                    kept.append(run)
                run = []
        if len(run) >= 2:
            kept.append(run)
    return kept
