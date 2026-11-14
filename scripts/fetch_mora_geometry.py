"""Download all public Mount Rainier trail geometry as WGS84 GeoJSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parkmatch.arcgis import fetch_geojson  # noqa: E402


DEFAULT_OUTPUT = ROOT / "data" / "raw" / "nps_mora_segments.geojson"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    geojson = fetch_geojson(
        "UNITCODE = 'MORA'",
        out_fields=(
            "OBJECTID,TRLNAME,TRLALTNAME,MAPLABEL,TRLSTATUS,TRLSURFACE,"
            "TRLTYPE,TRLCLASS,TRLUSE,UNITCODE,UNITNAME,EDITDATE,"
            "GEOMETRYID,FEATUREID"
        ),
        out_sr=4326,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    object_ids = {
        int(feature["properties"]["OBJECTID"])
        for feature in geojson["features"]
    }
    if len(object_ids) != len(geojson["features"]):
        raise RuntimeError("Downloaded GeoJSON contains duplicate OBJECTIDs")
    print(f"Saved {len(geojson['features'])} MORA features to {args.output}")


if __name__ == "__main__":
    main()

