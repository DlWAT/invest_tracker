"""Download and combine Philippine region/province GeoJSON for the map UI.

Fetches the per-region files from the faeldon/philippines-json-maps repo,
assigns a region name to each feature, and writes a single FeatureCollection
to static/ph_regions.geojson.

Run once:
    python fetch_regions.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

API = "https://api.github.com/repos/faeldon/philippines-json-maps/contents/2023/geojson/regions/medres"
RAW = "https://raw.githubusercontent.com/faeldon/philippines-json-maps/master/2023/geojson/regions/medres/"
UA = {"User-Agent": "Mozilla/5.0"}
OUT = Path(__file__).parent / "static" / "ph_regions.geojson"

# PSGC region code -> display name.
REGION_NAMES = {
    100000000: "Région I — Ilocos",
    200000000: "Région II — Vallée de Cagayan",
    300000000: "Région III — Luçon centrale",
    400000000: "Région IV-A — CALABARZON",
    1700000000: "MIMAROPA",
    500000000: "Région V — Bicol",
    600000000: "Région VI — Visayas occidentales",
    700000000: "Région VII — Visayas centrales",
    800000000: "Région VIII — Visayas orientales",
    900000000: "Région IX — Péninsule de Zamboanga",
    1000000000: "Région X — Mindanao du Nord",
    1100000000: "Région XI — Davao",
    1200000000: "Région XII — SOCCSKSARGEN",
    1300000000: "NCR — Metro Manila",
    1400000000: "CAR — Cordillère",
    1500000000: "BARMM",
    1600000000: "Région XIII — Caraga",
    1800000000: "Région de Negros (NIR)",
    1900000000: "BARMM",
}


def main() -> int:
    files = [
        "provdists-region-100000000.0.01.json",
        "provdists-region-1100000000.0.01.json",
        "provdists-region-1200000000.0.01.json",
        "provdists-region-1300000000.0.01.json",
        "provdists-region-1400000000.0.01.json",
        "provdists-region-1600000000.0.01.json",
        "provdists-region-1700000000.0.01.json",
        "provdists-region-1900000000.0.01.json",
        "provdists-region-200000000.0.01.json",
        "provdists-region-300000000.0.01.json",
        "provdists-region-400000000.0.01.json",
        "provdists-region-500000000.0.01.json",
        "provdists-region-600000000.0.01.json",
        "provdists-region-700000000.0.01.json",
        "provdists-region-800000000.0.01.json",
        "provdists-region-900000000.0.01.json",
    ]

    combined = {"type": "FeatureCollection", "features": []}
    seen_regions = {}

    for name in files:
        r = requests.get(RAW + name, headers=UA, timeout=60)
        if r.status_code != 200:
            print(f"  [!] {name} -> {r.status_code}")
            continue
        data = r.json()
        for feat in data["features"]:
            props = feat["properties"]
            code = props.get("adm1_psgc")
            region = REGION_NAMES.get(code, f"Région {code}")
            if code not in seen_regions:
                seen_regions[code] = region
                print(f"  region {code} -> {region} ({props.get('adm2_en')})")
            props["region_name"] = region
            combined["features"].append(feat)
        time.sleep(0.2)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(combined, ensure_ascii=False), encoding="utf-8")
    size = OUT.stat().st_size / 1024
    print(f"\n{len(combined['features'])} provinces, {len(seen_regions)} regions "
          f"-> {OUT} ({size:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
