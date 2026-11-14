"""Download the MORA trail overlay used by official NPS NPMap pages."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parkmatch.nps_carto import fetch_mora_trail_overlay  # noqa: E402


OUTPUT = ROOT / "data" / "raw" / "nps_mora_npmap_overlay.geojson"


def main() -> None:
    geojson = fetch_mora_trail_overlay()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Saved {len(geojson['features'])} NPMap features to {OUTPUT}")


if __name__ == "__main__":
    main()

