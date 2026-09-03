"""Flask web interface for browsing the listings database.

Serves a single-page UI (templates/index.html) and a JSON API for
filtering / sorting / paginating the collected listings.

Two countries are supported (Philippines and France), each with its own
SQLite database and GeoJSON. The active country is selected with a
``country`` cookie (``ph`` or ``fr``), switched from the UI.

Run:
    python app.py
Then open http://127.0.0.1:5000
"""

from __future__ import annotations

import bisect
import json
import os
import re
import sqlite3
import statistics
import threading
import unicodedata
from datetime import datetime, timezone, timedelta
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from uuid import uuid4

import requests
from flask import Flask, jsonify, render_template, request

from ph_scanner.config import (
    FAVORITE_ZONES as PH_FAVORITE_ZONES,
    MAX_PRICE_PHP,
    MIN_PRICE_PHP,
    PROVINCES as PH_PROVINCES,
    REGIONS as PH_REGIONS,
    assign_zone as PH_ASSIGN_ZONE,
)
from ph_scanner.models import Listing, normalize_type
from ph_scanner.runner import (
    SOURCES as PH_SOURCES,
    build_sources as PH_BUILD_SOURCES,
    collect,
)
from ph_scanner.storage import SCHEMA, Storage

from fr_scanner.config import (
    FAVORITE_ZONES as FR_FAVORITE_ZONES,
    MAX_PRICE_EUR,
    MIN_PRICE_EUR,
    PROVINCES as FR_PROVINCES,
    REGIONS as FR_REGIONS,
    assign_zone as FR_ASSIGN_ZONE,
)
from fr_scanner.runner import (
    SOURCES as FR_SOURCES,
    build_sources as FR_BUILD_SOURCES,
)

app = Flask(__name__)

_HERE = Path(__file__).parent

COUNTRIES = {
    "ph": {
        "id": "ph",
        "label": "Philippines",
        "flag": "🇵🇭",
        "db": _HERE / "data" / "listings.db",
        "geojson": _HERE / "static" / "ph_regions.geojson",
        "currency": "PHP",
        "symbol": "₱",
        "min_price": MIN_PRICE_PHP,
        "max_price": MAX_PRICE_PHP,
        "provinces": PH_PROVINCES,
        "regions": PH_REGIONS,
        "favorite_zones": PH_FAVORITE_ZONES,
        "assign_zone": PH_ASSIGN_ZONE,
        "sources": PH_SOURCES,
        "build_sources": PH_BUILD_SOURCES,
        "geocode_suffix": "Philippines",
        "map_center": [12.88, 121.77],
        "province_label": "Province",
    },
    "fr": {
        "id": "fr",
        "label": "France",
        "flag": "🇫🇷",
        "db": _HERE / "data" / "listings_fr.db",
        "geojson": _HERE / "static" / "fr_regions.geojson",
        "currency": "EUR",
        "symbol": "€",
        "min_price": MIN_PRICE_EUR,
        "max_price": MAX_PRICE_EUR,
        "provinces": FR_PROVINCES,
        "regions": FR_REGIONS,
        "favorite_zones": FR_FAVORITE_ZONES,
        "assign_zone": FR_ASSIGN_ZONE,
        "sources": FR_SOURCES,
        "build_sources": FR_BUILD_SOURCES,
        "geocode_suffix": "France",
        "map_center": [47.3, 1.9],
        "province_label": "Département",
    },
}

DEFAULT_COUNTRY = "ph"


def get_country() -> str:
    c = request.cookies.get("country")
    return c if c in COUNTRIES else DEFAULT_COUNTRY


def country_config() -> dict:
    return COUNTRIES[get_country()]


def country_public() -> dict:
    """JSON-safe subset of the active country config, injected into the UI."""
    cfg = country_config()
    return {
        "id": cfg["id"],
        "label": cfg["label"],
        "flag": cfg["flag"],
        "currency": cfg["currency"],
        "symbol": cfg["symbol"],
        "map_center": cfg["map_center"],
        "province_label": cfg["province_label"],
        "favorite_zones": cfg["favorite_zones"],
        "geojson": cfg["geojson"].name,
    }


# Shared state for the background collection job (used by the "collect" tab).
COLLECT = {
    "running": False,
    "country": None,
    "started": None,
    "finished": None,
    "stats": None,
    "error": None,
    "log": [],
}
_COLLECT_LOCK = threading.Lock()

_MAX_LOG_LINES = 2000


def _collect_log(line: str) -> None:
    with _COLLECT_LOCK:
        COLLECT["log"].append({
            "t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "line": line,
        })
        if len(COLLECT["log"]) > _MAX_LOG_LINES:
            del COLLECT["log"][:-_MAX_LOG_LINES]

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
    "CASE WHEN f.source IS NOT NULL THEN 1 ELSE 0 END AS is_favorite, "
    "CASE WHEN p.price_prev IS NOT NULL AND p.price_prev > 0 "
    "THEN ROUND((l.price_php - p.price_prev) * 100.0 / p.price_prev, 1) "
    "ELSE NULL END AS price_change_pct "
    "FROM listings l " + PRICE_JOIN +
    " LEFT JOIN favorites f ON f.source = l.source AND f.external_id = l.external_id"
)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(country_config()["db"]), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    items = [v.strip() for v in value.split(",") if v.strip()]
    return items or None


def _fav_zones_clause(zone_ids, table: str = "") -> tuple[str, list]:
    """Build a SQL fragment filtering listings by favorite-zone ids.

    ``table`` is an optional column prefix (e.g. ``"l."``). Returns
    ``(clause, params)`` where ``clause`` does not include a leading WHERE/AND.
    """
    cfg = country_config()
    zones = {z["id"]: z for z in cfg.get("favorite_zones", [])}
    selected = [zones[zid] for zid in (zone_ids or []) if zid in zones]
    if not selected:
        return "", []

    parts: list[str] = []
    params: list = []
    for z in selected:
        provs = list(z.get("provinces") or [])
        kws = list(z.get("keywords") or [])
        prov_cond = f"{table}province IN ({','.join('?' * len(provs))})" if provs else ""
        if kws:
            like_cond = " OR ".join(
                [f"({table}title LIKE ? OR {table}location_text LIKE ?)"] * len(kws)
            )
            kw_params: list = []
            for kw in kws:
                like = f"%{kw}%"
                kw_params += [like, like]
            if prov_cond:
                parts.append(f"({prov_cond} AND ({like_cond}))")
            else:
                parts.append(f"({like_cond})")
            params += provs + kw_params
        else:
            parts.append(f"({prov_cond})")
            params += provs

    return "(" + " OR ".join(parts) + ")", params


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

    fav_zones = _csv(request.args.get("fav_zones"))
    if fav_zones:
        zclause, zparams = _fav_zones_clause(fav_zones)
        if zclause:
            clauses.append(zclause)
            params += zparams

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
    if request.args.get("price_rise") == "1":
        clauses.append("p.price_prev IS NOT NULL AND l.price_php > p.price_prev")

    if request.args.get("favorites") == "1":
        clauses.append("EXISTS (SELECT 1 FROM favorites fv WHERE fv.source = l.source AND fv.external_id = l.external_id)")

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


def _json_list(raw) -> list:
    try:
        return json.loads(raw) if raw else []
    except (TypeError, json.JSONDecodeError):
        return []


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for col in ("amenities", "images"):
        d[col] = _json_list(d.get(col))
    d["thumb"] = d["images"][0] if d["images"] else None
    return d


def _attach_history(conn: sqlite3.Connection, items: list[dict]) -> None:
    """Attach each listing's full price history (for sparklines/graphs)."""
    if not items:
        return
    pairs = [(it["source"], it["external_id"]) for it in items]
    placeholders = ",".join("(?,?)" for _ in pairs)
    params = [v for pair in pairs for v in pair]
    rows = conn.execute(
        "SELECT source, external_id, price_php, seen_at FROM price_history "
        f"WHERE (source, external_id) IN ({placeholders}) ORDER BY seen_at ASC",
        params,
    ).fetchall()
    hist: dict[tuple, list[dict]] = {}
    for r in rows:
        hist.setdefault((r["source"], r["external_id"]), []).append(
            {"price_php": r["price_php"], "seen_at": r["seen_at"]}
        )
    for it in items:
        it["history"] = hist.get((it["source"], it["external_id"]), [])


def _num(value, cast=float):
    if value in (None, ""):
        return None
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def _norm_prov(value: str) -> str:
    """Normalize a province/department name to a comparable ASCII key."""
    s = unicodedata.normalize("NFD", (value or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s)


_PROV_TO_GEO: dict[str, dict[str, list[str]]] = {}


def _prov_to_geojson() -> dict[str, list[str]]:
    """Map each listing province slug to the geojson province name(s)."""
    cfg = country_config()
    cid = cfg["id"]
    if cid in _PROV_TO_GEO:
        return _PROV_TO_GEO[cid]
    geo = json.loads(cfg["geojson"].read_text(encoding="utf-8"))
    names = [f["properties"].get("adm2_en") or "" for f in geo["features"]]
    norm_by_name = {n: _norm_prov(n) for n in names if n}

    result: dict[str, list[str]] = {}
    for slug in cfg["provinces"]:
        if cid == "ph" and slug == "metro-manila":
            keys = [n for n in names if n.startswith("NCR") or n.startswith("City of Manila")]
        elif cid == "ph" and slug == "maguindanao":
            keys = [n for n in names if n.startswith("Maguindanao")]
        elif cid == "ph" and slug == "compostela-valley":
            keys = [n for n in names if n == "Davao de Oro"]
        else:
            target = _norm_prov(slug)
            keys = [n for n, nm in norm_by_name.items() if nm == target]
        result[slug] = keys
    _PROV_TO_GEO[cid] = result
    return result


def detect_province(location: str) -> str | None:
    low = (location or "").lower()
    for p in country_config()["provinces"]:
        if p in low or p.replace("-", " ") in low:
            return p
    return None


def geocode_location(query: str):
    """Best-effort Photon geocoding for a manual location string."""
    cfg = country_config()
    try:
        r = requests.get(
            "https://photon.komoot.io/api/",
            params={"q": f"{query}, {cfg['geocode_suffix']}", "limit": 1},
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
    return render_template("index.html", country=country_public())


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
        _attach_history(conn, items)
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
    cfg = country_config()
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
        zone_id=cfg["assign_zone"](province, title, location),
        amenities=[a.strip() for a in (data.get("amenities") or []) if a.strip()],
        images=[data["image"]] if data.get("image") else [],
        agent=(data.get("agent") or "").strip() or None,
        latitude=lat,
        longitude=lng,
        description=(data.get("description") or "").strip() or None,
    )

    storage = Storage(cfg["db"])
    try:
        status, _ = storage.upsert(listing)
        storage.commit()
    finally:
        storage.close()

    return jsonify({"status": status})


@app.route("/api/favorites", methods=["POST"])
def api_add_favorite():
    data = request.get_json(silent=True) or {}
    source = (data.get("source") or "").strip()
    external_id = (data.get("external_id") or "").strip()
    if not source or not external_id:
        return jsonify({"error": "source et external_id sont requis"}), 400

    conn = get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO favorites (source, external_id, created_at) VALUES (?,?,?)",
            (source, external_id, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/favorites", methods=["DELETE"])
def api_remove_favorite():
    data = request.get_json(silent=True) or {}
    source = (data.get("source") or "").strip()
    external_id = (data.get("external_id") or "").strip()
    if not source or not external_id:
        return jsonify({"error": "source et external_id sont requis"}), 400

    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM favorites WHERE source=? AND external_id=?",
            (source, external_id),
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/listing-history")
def api_listing_history():
    source = request.args.get("source", "").strip()
    external_id = request.args.get("external_id", "").strip()
    if not source or not external_id:
        return jsonify({"error": "source et external_id sont requis"}), 400

    conn = get_db()
    try:
        listing = conn.execute(
            "SELECT * FROM listings WHERE source=? AND external_id=?",
            (source, external_id),
        ).fetchone()
        history = conn.execute(
            "SELECT price_php, seen_at FROM price_history "
            "WHERE source=? AND external_id=? ORDER BY seen_at ASC",
            (source, external_id),
        ).fetchall()
    finally:
        conn.close()

    if listing is None:
        return jsonify({"error": "annonce introuvable"}), 404

    return jsonify({
        "listing": _row_to_dict(listing),
        "history": [{"price_php": r["price_php"], "seen_at": r["seen_at"]} for r in history],
    })


@app.route("/api/stats")
def api_stats():
    conn = get_db()
    try:
        zclause, zparams = _fav_zones_clause(_csv(request.args.get("fav_zones")), "l.")
        total = conn.execute(
            "SELECT COUNT(*) FROM listings l" + (f" WHERE {zclause}" if zclause else ""),
            zparams,
        ).fetchone()[0]
        favorites = conn.execute(
            "SELECT COUNT(*) FROM favorites f "
            "JOIN listings l ON f.source = l.source AND f.external_id = l.external_id"
            + (f" WHERE {zclause}" if zclause else ""),
            zparams,
        ).fetchone()[0]

        def _price_change(operator: str) -> int:
            conds = [f"p.price_prev IS NOT NULL AND l.price_php {operator} p.price_prev"]
            if zclause:
                conds.append(zclause)
            return conn.execute(
                "SELECT COUNT(*) FROM listings l " + PRICE_JOIN +
                " WHERE " + " AND ".join(conds),
                zparams,
            ).fetchone()[0]

        drops = _price_change("<")
        rises = _price_change(">")

        zones_cond = ["zone_id IS NOT NULL"]
        if zclause:
            zones_cond.append(zclause)
        zones = conn.execute(
            "SELECT COUNT(DISTINCT zone_id) FROM listings l "
            "WHERE " + " AND ".join(zones_cond),
            zparams,
        ).fetchone()[0]
        newest = conn.execute(
            "SELECT MAX(first_seen) FROM listings l" + (f" WHERE {zclause}" if zclause else ""),
            zparams,
        ).fetchone()[0]
        return jsonify({
            "total": total,
            "favorites": favorites,
            "price_drops": drops,
            "price_rises": rises,
            "zones": zones,
            "newest": newest,
        })
    finally:
        conn.close()


@app.route("/api/map/metrics")
def api_map_metrics():
    conn = get_db()
    try:
        zclause, zparams = _fav_zones_clause(_csv(request.args.get("fav_zones")), "l.")
        rows = conn.execute(
            "SELECT l.province, l.price_php, l.price_per_sqm FROM listings l"
            + (f" WHERE {zclause}" if zclause else ""),
            zparams,
        ).fetchall()
    finally:
        conn.close()

    by_prov: dict[str, dict] = {}
    for r in rows:
        slug = r["province"]
        if not slug:
            continue
        b = by_prov.setdefault(slug, {"n": 0, "prices": [], "psqm": []})
        b["n"] += 1
        if r["price_php"]:
            b["prices"].append(r["price_php"])
        if r["price_per_sqm"]:
            b["psqm"].append(r["price_per_sqm"])

    slug_map = _prov_to_geojson()
    metrics: dict[str, dict] = {}
    for slug, b in by_prov.items():
        entry = {
            "count": b["n"],
            "median_price": round(statistics.median(b["prices"])) if b["prices"] else None,
            "median_psqm": round(statistics.median(b["psqm"])) if b["psqm"] else None,
        }
        for name in slug_map.get(slug, []):
            metrics[name] = entry

    return jsonify({"metrics": metrics})


@app.route("/api/map/listings")
def api_map_listings():
    """Lightweight GPS listings within a bounding box, for zoom-in markers."""
    def num(name: str) -> float | None:
        v = request.args.get(name)
        return float(v) if v not in (None, "") else None

    min_lat, max_lat = num("min_lat"), num("max_lat")
    min_lng, max_lng = num("min_lng"), num("max_lng")

    zclause, zparams = _fav_zones_clause(_csv(request.args.get("fav_zones")), "l.")

    q = (
        "SELECT l.source, l.external_id, l.url, l.title, l.price_php, l.price_per_sqm, "
        "l.property_type, l.location_text, l.province, l.zone_id, l.latitude, l.longitude "
        "FROM listings l WHERE l.latitude IS NOT NULL AND l.longitude IS NOT NULL"
    )
    params: list = []
    if zclause:
        q += f" AND {zclause}"
        params += zparams
    if min_lat is not None and max_lat is not None and min_lng is not None and max_lng is not None:
        q += " AND l.latitude BETWEEN ? AND ? AND l.longitude BETWEEN ? AND ?"
        params += [min_lat, max_lat, min_lng, max_lng]
        q += " LIMIT 800"

    conn = get_db()
    try:
        rows = conn.execute(q, params).fetchall()
    finally:
        conn.close()

    return jsonify({"items": [dict(r) for r in rows]})


@app.route("/api/trends")
def api_trends():
    """Price drops and rises observed over the last ``days`` days."""
    days = 30
    conn = get_db()
    try:
        zclause, zparams = _fav_zones_clause(_csv(request.args.get("fav_zones")), "l.")
        rows = conn.execute(
            "SELECT h.source, h.external_id, h.price_php, h.seen_at, "
            "l.url, l.title, l.location_text, l.province, l.zone_id, "
            "l.property_type, l.price_per_sqm, l.beds, l.area_sqm, "
            "l.images, l.amenities, l.agent, l.is_featured, l.latitude, "
            "l.first_seen "
            "FROM price_history h "
            "JOIN listings l ON l.source = h.source AND l.external_id = h.external_id "
            + (f" WHERE {zclause} " if zclause else "") +
            "ORDER BY h.source, h.external_id, h.seen_at ASC, h.rowid ASC",
            zparams,
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return jsonify({"window_days": days, "drops": [], "rises": []})

    by_listing: dict[tuple, list] = {}
    for r in rows:
        by_listing.setdefault((r["source"], r["external_id"]), []).append(r)

    max_seen = max(datetime.fromisoformat(r["seen_at"]) for r in rows)
    cutoff = max_seen - timedelta(days=days)

    drops: list[dict] = []
    rises: list[dict] = []
    for entries in by_listing.values():
        if len(entries) < 2:
            continue
        latest = entries[-1]
        base = None
        for e in entries:
            if datetime.fromisoformat(e["seen_at"]) <= cutoff:
                base = e
            else:
                break
        if base is None:
            base = entries[0]

        cur, prev = latest["price_php"], base["price_php"]
        if not cur or not prev or cur == prev:
            continue
        change = cur - prev
        images = _json_list(latest["images"])
        item = {
            "source": latest["source"], "external_id": latest["external_id"],
            "url": latest["url"], "title": latest["title"],
            "location_text": latest["location_text"], "province": latest["province"],
            "zone_id": latest["zone_id"], "property_type": latest["property_type"],
            "price_per_sqm": latest["price_per_sqm"], "beds": latest["beds"],
            "area_sqm": latest["area_sqm"],
            "images": images, "thumb": images[0] if images else None,
            "amenities": _json_list(latest["amenities"]),
            "agent": latest["agent"],
            "is_featured": bool(latest["is_featured"]),
            "latitude": latest["latitude"],
            "first_seen": latest["first_seen"],
            "price_php": cur, "price_prev": prev,
            "price_change_pct": round(change * 100.0 / prev, 1),
            "changed_at": latest["seen_at"],
        }
        (drops if change < 0 else rises).append(item)

    drops.sort(key=lambda x: x["price_change_pct"])
    rises.sort(key=lambda x: x["price_change_pct"], reverse=True)

    return jsonify({"window_days": days, "drops": drops, "rises": rises})


@app.route("/api/analytics/evolution")
def api_analytics_evolution():
    conn = get_db()
    try:
        zclause, zparams = _fav_zones_clause(_csv(request.args.get("fav_zones")), "l.")
        rows = conn.execute(
            "SELECT h.external_id, h.price_php, h.seen_at, l.province "
            "FROM price_history h "
            "JOIN listings l ON l.source = h.source AND l.external_id = h.external_id "
            + (f" WHERE {zclause} " if zclause else "") +
            "ORDER BY h.seen_at ASC, h.rowid ASC",
            zparams,
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return jsonify({"dates": [], "overall": {"median_price": [], "count": []}, "provinces": {}})

    series: dict[str, dict] = {}
    prov_of: dict[str, str] = {}
    for r in rows:
        day = r["seen_at"][:10]
        entry = series.setdefault(r["external_id"], {"ds": [], "ps": []})
        entry["ds"].append(day)
        entry["ps"].append(r["price_php"])
        if r["province"]:
            prov_of[r["external_id"]] = r["province"]

    dates = sorted({d for e in series.values() for d in e["ds"]})
    prov_names = sorted({p for p in prov_of.values() if p})

    def median(xs: list) -> int | None:
        return round(statistics.median(xs)) if xs else None

    overall_median: list = []
    overall_count: list = []
    prov_series = {p: {"median_price": [], "count": []} for p in prov_names}

    for day in dates:
        prices: list = []
        prov_prices = {p: [] for p in prov_names}
        for ext_id, e in series.items():
            idx = bisect.bisect_right(e["ds"], day) - 1
            if idx < 0:
                continue
            price = e["ps"][idx]
            if price is None:
                continue
            prices.append(price)
            prov = prov_of.get(ext_id)
            if prov in prov_prices:
                prov_prices[prov].append(price)

        overall_median.append(median(prices))
        overall_count.append(len(prices))
        for p in prov_names:
            plist = prov_prices[p]
            prov_series[p]["median_price"].append(median(plist))
            prov_series[p]["count"].append(len(plist))

    return jsonify({
        "dates": dates,
        "overall": {"median_price": overall_median, "count": overall_count},
        "provinces": prov_series,
    })


@app.route("/api/collect/start", methods=["POST"])
def api_collect_start():
    cfg = country_config()
    with _COLLECT_LOCK:
        if COLLECT["running"]:
            return jsonify({"ok": False, "error": "already running"}), 409
        COLLECT.update({
            "running": True,
            "country": cfg["id"],
            "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "finished": None,
            "stats": None,
            "error": None,
            "log": [],
        })

    def worker() -> None:
        storage = None
        stats = None
        try:
            sources = cfg["build_sources"](
                list(cfg["sources"]), 1.0, cfg["min_price"], cfg["max_price"]
            )
            storage = Storage(cfg["db"])
            stats = collect(sources, storage, cfg["provinces"], progress=_collect_log)
        except Exception as exc:  # noqa: BLE001
            _collect_log(f"[error] {exc}")
            with _COLLECT_LOCK:
                COLLECT["error"] = str(exc)
        finally:
            if storage is not None:
                storage.close()
            with _COLLECT_LOCK:
                COLLECT["running"] = False
                COLLECT["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                if COLLECT["error"] is None:
                    COLLECT["stats"] = stats

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/collect/status")
def api_collect_status():
    with _COLLECT_LOCK:
        return jsonify({
            "running": COLLECT["running"],
            "country": COLLECT["country"],
            "started": COLLECT["started"],
            "finished": COLLECT["finished"],
            "stats": COLLECT["stats"],
            "error": COLLECT["error"],
            "log": list(COLLECT["log"]),
        })


@app.route("/api/facets")
def api_facets():
    cfg = country_config()
    conn = get_db()
    try:
        def col(query: str):
            return [r[0] for r in conn.execute(query).fetchall()]

        price = conn.execute(
            "SELECT MIN(price_php), MAX(price_php) FROM listings"
        ).fetchone()
        return jsonify({
            "regions": cfg["regions"],
            "types": col("SELECT DISTINCT property_type FROM listings WHERE property_type IS NOT NULL ORDER BY property_type"),
            "zones": col("SELECT DISTINCT zone_id FROM listings WHERE zone_id IS NOT NULL ORDER BY zone_id"),
            "price_min": price[0] or 0,
            "price_max": price[1] or 0,
            "currency": cfg["currency"],
            "symbol": cfg["symbol"],
        })
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes"),
    )
