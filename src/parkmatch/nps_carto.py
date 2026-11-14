"""Client for the trail overlay used by official NPS NPMap pages."""

from __future__ import annotations

from typing import Any

import requests


NPS_CARTO_SQL_URL = "https://carto.nps.gov/user/parktiles/api/v2/sql"


class NPSCartoQueryError(RuntimeError):
    """Raised when the NPS Carto endpoint returns an invalid response."""


def fetch_mora_trail_overlay(
    *,
    timeout_seconds: int = 90,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Return the MORA trail overlay used by official NPS interactive maps."""

    client = session or requests
    response = client.get(
        NPS_CARTO_SQL_URL,
        params={
            "format": "geojson",
            "q": 'SELECT * FROM "trail" WHERE "unit_code"=\'mora\'',
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise NPSCartoQueryError(str(payload["error"]))
    if payload.get("type") != "FeatureCollection":
        raise NPSCartoQueryError(
            f"Expected GeoJSON FeatureCollection, got {payload.get('type')!r}"
        )
    return payload

