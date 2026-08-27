"""Flask web interface for browsing the listings database.

Serves a single-page UI (templates/index.html) and a JSON API for
filtering / sorting / paginating the collected listings.

Run:
    python app.py
Then open http://127.0.0.1:5000
"""

from __future__ import annotations

import json
import sqlite3
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from uuid import uuid4

import requests
from flask import Flask, jsonify, render_template, request

from ph_scanner.config import PROVINCES, REGIONS, assign_zone
from ph_scanner.models import Listing, normalize_type
from ph_scanner.storage import Storage

DB_PATH = Path(__file__).parent / "data" / "listings.db"

app = Flask(__name__)

SORT_FIELDS = {
    "price_asc": "price_php ASC",
    "price_desc": "price_php DESC",
    "psqm_asc": "price_per_sqm ASC NULLS LAST",
    "psqm_desc": "price_per_sqm DESC NULLS LAST",
    "area_asc": "area_sqm ASC NULLS LAST",
    "area_desc": "area_sqm DESC NULLS LAST",
    "beds_desc": "beds DESC NULLS LAST",
    "newest": "first_seen DESC",
    "cheapest_psqm": "price_per_sqm ASC NULLS LAST",
    "drop_desc": "price_change_pct ASC NULLS LAST",
    "rise_desc": "price_change_pct DESC NULLS LAST",
}

# Fields that can be filtered via CSV query params.
LIST_FILTERS = ("province", "zone_id", "property_type")

# JOIN that exposes the previous price (2nd most recent price_history entry)
# plus the percentage change vs. the current price.
PRICE_JOIN = """
LEFT JOIN (
    SELECT source, external_id, price_php AS price_prev
    FROM (
        SELECT source, external_id, price_php,
               ROW_NUMBER() OVER (PARTITION BY source, external_id
                                  ORDER BY seen_at DESC, rowid DESC) AS rn
        FROM price_history
    ) WHERE rn = 2
) p ON p.source = l.source AND p.external_id = l.external_id
"""

LISTING_SELECT = (
    "SELECT l.*, p.price_prev, "
    "CASE WHEN p.price_prev IS NOT NULL AND p.price_prev > 0 "
    "THEN ROUND((l.price_php - p.price_prev) * 100.0 / p.price_prev, 1) "
    "ELSE NULL END AS price_change_pct "
    "FROM listings l " + PRICE_JOIN
)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    items = [v.strip() for v in value.split(",") if v.strip()]
    return items or None


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points, in kilometres."""
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _where(request) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []

    q = request.args.get("q", "").strip()
    if q:
        like = f"%{q}%"
        clauses.append("(title LIKE ? OR location_text LIKE ? OR description LIKE ? OR agent LIKE ?)")
        params += [like, like, like, like]

    for field in LIST_FILTERS:
        values = _csv(request.args.get(field))
        if values:
            if "null" in values:
                clauses.append(f"({field} IS NULL OR {field} IN ({','.join('?' * (len(values) - 1))}))")
                params += [v for v in values if v != "null"]
            else:
                clauses.append(f"{field} IN ({','.join('?' * len(values))})")
                params += values

    def num(name: str) -> float | None:
        v = request.args.get(name)
        return float(v) if v not in (None, "") else None

    min_price = num("min_price")
    if min_price is not None:
        clauses.append("price_php >= ?")
        params.append(min_price)

    max_price = num("max_price")
    if max_price is not None:
        clauses.append("price_php <= ?")
        params.append(max_price)

    min_beds = num("min_beds")
    if min_beds is not None:
        clauses.append("COALESCE(beds, 0) >= ?")
        params.append(int(min_beds))

    min_area = num("min_area")
    if min_area is not None:
        clauses.append("COALESCE(area_sqm, 0) >= ?")
        params.append(min_area)

    max_area = num("max_area")
    if max_area is not None:
        clauses.append("COALESCE(area_sqm, 0) <= ?")
        params.append(max_area)

    if request.args.get("has_gps") == "1":
        clauses.append("latitude IS NOT NULL")
    if request.args.get("featured") == "1":
        clauses.append("is_featured = 1")
    if request.args.get("price_drop") == "1":
        clauses.append("p.price_prev IS NOT NULL AND l.price_php < p.price_prev")

    # Geo radius: pre-filter with a bounding box, exact filter later in Python.
    lat = num("lat")
    lng = num("lng")
    radius = num("radius")
    if lat is not None and lng is not None and radius and radius > 0:
        dlat = radius / 111.32
        dlng = radius / (111.32 * max(0.05, abs(cos(radians(lat)))))
        clauses.append("latitude BETWEEN ? AND ?")
        clauses.append("longitude BETWEEN ? AND ?")
        params += [lat - dlat, lat + dlat, lng - dlng, lng + dlng]

    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for col in ("amenities", "images"):
        raw = d.get(col)
        try:
            d[col] = json.loads(raw) if raw else []
        except (TypeError, json.JSONDecodeError):
            d[col] = []
    d["thumb"] = d["images"][0] if d["images"] else None
    return d


def _num(value, cast=float):
    if value in (None, ""):
        return None
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def detect_province(location: str) -> str | None:
    low = (location or "").lower()
    for p in PROVINCES:
        if p in low or p.replace("-", " ") in low:
            return p
    return None


def geocode_location(query: str):
    """Best-effort Photon geocoding for a manual location string."""
    try:
        r = requests.get(
            "https://photon.komoot.io/api/",
            params={"q": f"{query}, Philippines", "limit": 1},
            headers={"User-Agent": "ph-scanner/1.0"},
            timeout=15,
        )
        feats = r.json().get("features", [])
        if feats:
            lng, lat = feats[0]["geometry"]["coordinates"]
            return lat, lng
    except Exception:  # noqa: BLE001
        pass
    return None, None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/listings")
def api_listings():
    where, params = _where(request)

    sort = request.args.get("sort", "newest")
    order = SORT_FIELDS.get(sort, "first_seen DESC")

    page = max(1, int(request.args.get("page", 1)))
    per_page = min(100, max(6, int(request.args.get("per_page", 24))))

    lat = request.args.get("lat")
    lng = request.args.get("lng")
    radius = request.args.get("radius")

    conn = get_db()
    try:
        if lat and lng and radius:
            lat_f, lng_f, radius_f = float(lat), float(lng), float(radius)
            candidates = conn.execute(
                f"{LISTING_SELECT}{where} ORDER BY {order}", params
            ).fetchall()
            exact = [
                r for r in candidates
                if r["latitude"] is not None and r["longitude"] is not None
                and haversine_km(lat_f, lng_f, r["latitude"], r["longitude"]) <= radius_f
            ]
            total = len(exact)
            start = (page - 1) * per_page
            items = [_row_to_dict(r) for r in exact[start:start + per_page]]
        else:
            total = conn.execute(
                f"SELECT COUNT(*) FROM listings l {PRICE_JOIN}{where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"{LISTING_SELECT}{where} ORDER BY {order} "
                f"LIMIT ? OFFSET ?",
                params + [per_page, (page - 1) * per_page],
            ).fetchall()
            items = [_row_to_dict(r) for r in rows]
    finally:
        conn.close()

    return jsonify({
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
        "items": items,
    })


@app.route("/api/listings", methods=["POST"])
def api_add_listing():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    price = _num(data.get("price_php"), int)
    location = (data.get("location_text") or "").strip()
    if not title or price is None or not location:
        return jsonify({"error": "title, price_php et location_text sont requis"}), 400

    url = (data.get("url") or "").strip()
    external_id = url if url else f"manual-{uuid4().hex[:12]}"

    lat = _num(data.get("latitude"))
    lng = _num(data.get("longitude"))
    if lat is None or lng is None:
        lat, lng = geocode_location(location)

    province = detect_province(location)
    area = _num(data.get("area_sqm"))
    listing = Listing(
        source="facebook",
        external_id=external_id,
        url=url,
        title=title,
        price_php=price,
        price_per_sqm=round(price / area, 2) if (price and area) else None,
        beds=_num(data.get("beds"), int),
        baths=_num(data.get("baths"), int),
        area_sqm=area,
        property_type=normalize_type(data.get("property_type") or "other"),
        location_text=location,
        province=province,
        zone_id=assign_zone(province, title, location),
        amenities=[a.strip() for a in (data.get("amenities") or []) if a.strip()],
        images=[data["image"]] if data.get("image") else [],
        agent=(data.get("agent") or "").strip() or None,
        latitude=lat,
        longitude=lng,
        description=(data.get("description") or "").strip() or None,
    )

    storage = Storage(DB_PATH)
    try:
        status, _ = storage.upsert(listing)
        storage.commit()
    finally:
        storage.close()

    return jsonify({"status": status})


@app.route("/api/facets")
def api_facets():
    conn = get_db()
    try:
        def col(query: str):
            return [r[0] for r in conn.execute(query).fetchall()]

        price = conn.execute(
            "SELECT MIN(price_php), MAX(price_php) FROM listings"
        ).fetchone()
        return jsonify({
            "regions": REGIONS,
            "types": col("SELECT DISTINCT property_type FROM listings WHERE property_type IS NOT NULL ORDER BY property_type"),
            "zones": col("SELECT DISTINCT zone_id FROM listings WHERE zone_id IS NOT NULL ORDER BY zone_id"),
            "price_min": price[0] or 0,
            "price_max": price[1] or 0,
        })
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
