"""Download Washington State Trails Database lines around Mount Rainier.

Source: Washington State Recreation and Conservation Office, Trails Database
public view (https://trails-wa-rco.hub.arcgis.com/pages/data-download).
The publisher states the data is for informational purposes only and must
not be used for navigation. The raw download is saved unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "raw" / "wa_rco_trails_mora.geojson"
QUERY_URL = (
    "https://services2.arcgis.com/TGEC20q86HQAeMS6/arcgis/rest/services/"
    "WA_RCO_Trails_Database_Public_View/FeatureServer/0/query"
)
# West, south, east, north in WGS84; covers the park and its trailheads.
MORA_ENVELOPE = "-122.00,46.68,-121.42,47.05"
PAGE_SIZE = 500


def fetch_page(offset: int) -> dict:
    response = requests.get(
        QUERY_URL,
        params={
            "where": "1=1",
            "geometry": MORA_ENVELOPE,
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "outSR": 4326,
            "orderByFields": "OBJECTID",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
            "f": "geojson",
        },
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    if "features" not in payload:
        raise RuntimeError(f"Unexpected response: {payload}")
    return payload


def main() -> None:
    features: list[dict] = []
    while True:
        page = fetch_page(len(features))
        features.extend(page["features"])
        if len(page["features"]) < PAGE_SIZE:
            break
    object_ids = [feature["properties"]["OBJECTID"] for feature in features]
    if len(object_ids) != len(set(object_ids)):
        raise RuntimeError("Duplicate OBJECTID values across pages")
    collection = {"type": "FeatureCollection", "features": features}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(features)} trail segments to {OUTPUT}")


if __name__ == "__main__":
    main()
