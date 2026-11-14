"""Candidate-route selection based on transparent name rules."""

from __future__ import annotations

from typing import Any


def normalized_name(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def select_by_names(
    features: list[dict[str, Any]], names: list[str]
) -> list[dict[str, Any]]:
    wanted = {normalized_name(name) for name in names}
    return [
        feature
        for feature in features
        if normalized_name(feature.get("properties", {}).get("TRLNAME")) in wanted
    ]


def object_id(feature: dict[str, Any]) -> int:
    return int(feature["properties"]["OBJECTID"])

