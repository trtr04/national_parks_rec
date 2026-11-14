"""Small ArcGIS REST client used by the geometry preparation pipeline."""

from __future__ import annotations

from typing import Any

import requests


MORA_TRAILS_QUERY_URL = (
    "https://mapservices.nps.gov/arcgis/rest/services/"
    "NationalDatasets/NPS_Public_Trails_Geographic/"
    "FeatureServer/0/query"
)


class ArcGISQueryError(RuntimeError):
    """Raised when ArcGIS returns an application-level error."""


def fetch_geojson(
    where: str,
    *,
    out_fields: str = "*",
    out_sr: int = 4326,
    query_url: str = MORA_TRAILS_QUERY_URL,
    timeout_seconds: int = 60,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Query trail features and return a GeoJSON FeatureCollection.

    ArcGIS can return HTTP 200 together with an ``error`` object, so both the
    HTTP status and the response body are checked.
    """

    client = session or requests
    response = client.get(
        query_url,
        params={
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": out_sr,
            "f": "geojson",
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()

    if "error" in payload:
        raise ArcGISQueryError(str(payload["error"]))
    if payload.get("type") != "FeatureCollection":
        raise ArcGISQueryError(
            f"Expected GeoJSON FeatureCollection, got {payload.get('type')!r}"
        )

    features = payload.get("features")
    if not isinstance(features, list):
        raise ArcGISQueryError("GeoJSON response does not contain a feature list")

    return payload

