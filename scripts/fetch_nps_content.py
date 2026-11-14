"""Download Mount Rainier content records from the NPS Data API.

Saves the raw responses unchanged under data/raw/nps_api/. Set the
NPS_API_KEY environment variable to your own key (free from
https://www.nps.gov/subjects/developer/get-started.htm). Without it the
script uses the shared, rate-limited DEMO_KEY.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data" / "raw" / "nps_api"
BASE_URL = "https://developer.nps.gov/api/v1"
PARK_CODE = "mora"
ENDPOINTS = {
    "thingstodo": {"parkCode": PARK_CODE, "limit": 200},
    "parks": {"parkCode": PARK_CODE},
    "places": {"parkCode": PARK_CODE, "limit": 500},
}


def fetch(endpoint: str, params: dict[str, object], api_key: str) -> dict:
    response = requests.get(
        f"{BASE_URL}/{endpoint}",
        params=params,
        headers={"X-Api-Key": api_key},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if "data" not in payload:
        raise RuntimeError(f"Unexpected response from /{endpoint}: {payload}")
    return payload


def main() -> None:
    api_key = os.environ.get("NPS_API_KEY", "DEMO_KEY")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for endpoint, params in ENDPOINTS.items():
        payload = fetch(endpoint, params, api_key)
        total = int(payload.get("total", len(payload["data"])))
        if total > len(payload["data"]):
            raise RuntimeError(
                f"/{endpoint} returned {len(payload['data'])} of {total} records; "
                "raise the limit."
            )
        output = OUTPUT_DIR / f"{endpoint}_{PARK_CODE}.json"
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Saved {len(payload['data'])} /{endpoint} records to {output}")


if __name__ == "__main__":
    main()
