"""Geocode the distinct location_text values and fill listing lat/lng.

Uses Photon (OpenStreetMap-based) geocoder — free, no API key.

Run once (idempotent, caches results):
    python geocode.py --db data/listings.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

PHOTON_URL = "https://photon.komoot.io/api/"
UA = {"User-Agent": "ph-scanner/1.0"}

GEOCODE_SCHEMA = """
CREATE TABLE IF NOT EXISTS geocache (
    location_text TEXT PRIMARY KEY,
    lat REAL,
    lng REAL,
    label TEXT
);
"""


def geocode(query: str) -> tuple[float, float, str] | None:
    try:
        r = requests.get(PHOTON_URL, params={"q": query, "limit": 1},
                         headers=UA, timeout=30)
        r.raise_for_status()
    except requests.RequestException as exc:
        print(f"    [!] geocode error for {query!r}: {exc}")
        return None

    feats = r.json().get("features", [])
    if not feats:
        return None
    props = feats[0]["properties"]
    lng, lat = feats[0]["geometry"]["coordinates"]
    label = ", ".join(filter(None, [props.get("name"), props.get("state"),
                                    props.get("country")]))
    return lat, lng, label


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/listings.db")
    parser.add_argument("--delay", type=float, default=0.6)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.executescript(GEOCODE_SCHEMA)

    locations = [r[0] for r in conn.execute(
        "SELECT DISTINCT location_text FROM listings "
        "WHERE location_text IS NOT NULL AND location_text != '' "
        "ORDER BY location_text"
    ).fetchall()]

    print(f"{len(locations)} localisations uniques à géocoder\n")

    for i, loc in enumerate(locations, 1):
        cached = conn.execute(
            "SELECT lat, lng, label FROM geocache WHERE location_text=?", (loc,)
        ).fetchone()
        if cached:
            lat, lng, label = cached
            print(f"[{i}/{len(locations)}] {loc:40s} -> (cache) {lat:.4f},{lng:.4f}")
        else:
            lat = lng = label = None
            result = geocode(f"{loc}, Philippines")
            if result:
                lat, lng, label = result
                conn.execute(
                    "INSERT OR REPLACE INTO geocache (location_text, lat, lng, label) "
                    "VALUES (?,?,?,?)", (loc, lat, lng, label)
                )
            else:
                print(f"[{i}/{len(locations)}] {loc:40s} -> INTROUVABLE")
            conn.commit()
            if lat is not None:
                print(f"[{i}/{len(locations)}] {loc:40s} -> {lat:.4f},{lng:.4f} ({label})")
            time.sleep(args.delay)

    # Fill listings coordinates from cache.
    updated = 0
    for (loc, lat, lng) in conn.execute(
        "SELECT location_text, lat, lng FROM geocache WHERE lat IS NOT NULL"
    ).fetchall():
        cur = conn.execute(
            "UPDATE listings SET latitude=?, longitude=? WHERE location_text=?",
            (lat, lng, loc),
        )
        updated += cur.rowcount
    conn.commit()

    n = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
    ).fetchone()[0]
    print(f"\nDone. {updated} annonces mises à jour, {n} avec coordonnées au total.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
