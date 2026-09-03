"""Download and combine French department GeoJSON for the map UI.

Fetches the departments file from the gregoiredavid/france-geojson repo, tags
each feature with its region name, and writes a single FeatureCollection to
static/fr_regions.geojson using the same property keys as the Philippine map
(``adm2_en`` + ``region_name``).

Run once:
    python fetch_fr_regions.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

URL = "https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/departements.geojson"
OUT = Path(__file__).parent / "static" / "fr_regions.geojson"

# Department code -> region name (13 metropolitan regions).
REGIONS = {
    "Auvergne-Rhône-Alpes": ["01", "03", "07", "15", "26", "38", "42", "43",
                             "63", "69", "73", "74"],
    "Bourgogne-Franche-Comté": ["21", "25", "39", "58", "70", "71", "89", "90"],
    "Bretagne": ["22", "29", "35", "56"],
    "Centre-Val de Loire": ["18", "28", "36", "37", "41", "45"],
    "Corse": ["2A", "2B"],
    "Grand Est": ["08", "10", "51", "52", "54", "55", "57", "67", "68", "88"],
    "Hauts-de-France": ["02", "59", "60", "62", "80"],
    "Île-de-France": ["75", "77", "78", "91", "92", "93", "94", "95"],
    "Normandie": ["14", "27", "50", "61", "76"],
    "Nouvelle-Aquitaine": ["16", "17", "19", "23", "24", "33", "40", "47",
                           "64", "79", "86", "87"],
    "Occitanie": ["09", "11", "12", "30", "31", "32", "34", "46", "48", "65",
                  "66", "81", "82"],
    "Pays de la Loire": ["44", "49", "53", "72", "85"],
    "Provence-Alpes-Côte d'Azur": ["04", "05", "06", "13", "83", "84"],
}

REGION_BY_CODE: dict[str, str] = {}
for region, codes in REGIONS.items():
    for code in codes:
        REGION_BY_CODE[code] = region


def main() -> int:
    r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    r.raise_for_status()
    data = r.json()

    seen: set[str] = set()
    for feat in data["features"]:
        props = feat["properties"]
        code = props.get("code", "")
        props["adm2_en"] = props.get("nom", "")
        props["region_name"] = REGION_BY_CODE.get(code, "France")
        seen.add(code)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    size = OUT.stat().st_size / 1024
    print(f"{len(data['features'])} departements -> {OUT} ({size:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
