"""SQLite storage for listings with dedup and simple history tracking."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Listing

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    source        TEXT NOT NULL,
    external_id   TEXT NOT NULL,
    url           TEXT,
    title         TEXT,
    price_php     INTEGER,
    price_per_sqm REAL,
    beds          INTEGER,
    baths         INTEGER,
    area_sqm      REAL,
    property_type TEXT,
    location_text TEXT,
    province      TEXT,
    zone_id       TEXT,
    amenities     TEXT,
    images        TEXT,
    agent         TEXT,
    is_featured   INTEGER,
    has_virtual_tour INTEGER,
    latitude      REAL,
    longitude     REAL,
    description   TEXT,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    PRIMARY KEY (source, external_id)
);

CREATE TABLE IF NOT EXISTS price_history (
    source       TEXT NOT NULL,
    external_id  TEXT NOT NULL,
    price_php    INTEGER,
    seen_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_listings_zone ON listings(zone_id);
CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price_php);
"""


class Storage:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # timeout + busy_timeout: wait instead of failing when another
        # process (e.g. the web app) briefly holds the lock.
        self.conn = sqlite3.connect(str(self.db_path), timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()

    def commit(self) -> None:
        self.conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def upsert(self, listing: Listing) -> tuple[str, int | None]:
        """Insert or update a listing. Returns (status, price_diff).

        status is one of "new", "updated", "unchanged", "price_change".
        price_diff is the signed change when status == "price_change".
        """
        now = self._now()
        data = listing.to_dict()
        cur = self.conn.execute(
            "SELECT price_php FROM listings WHERE source=? AND external_id=?",
            (listing.source, listing.external_id),
        )
        row = cur.fetchone()

        if row is None:
            self.conn.execute(
                """
                INSERT INTO listings (
                    source, external_id, url, title, price_php, price_per_sqm,
                    beds, baths, area_sqm, property_type, location_text, province,
                    zone_id, amenities, images, agent, is_featured, has_virtual_tour,
                    latitude, longitude, description, first_seen, last_seen
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    listing.source, listing.external_id, listing.url, listing.title,
                    listing.price_php, listing.price_per_sqm, listing.beds,
                    listing.baths, listing.area_sqm, listing.property_type,
                    listing.location_text, listing.province, listing.zone_id,
                    json.dumps(listing.amenities), json.dumps(listing.images),
                    listing.agent, int(listing.is_featured),
                    int(listing.has_virtual_tour), listing.latitude,
                    listing.longitude, listing.description, now, now,
                ),
            )
            self._record_price(listing, now)
            return "new", None

        old_price = row[0]
        price_changed = bool(listing.price_php and old_price != listing.price_php)

        # Always refresh fields so re-scrapes fix missing images/description.
        self.conn.execute(
            """
            UPDATE listings SET
                price_php=?, price_per_sqm=?, title=?, beds=?, baths=?,
                area_sqm=?, location_text=?, province=?, zone_id=?, amenities=?,
                images=?, agent=?, is_featured=?, has_virtual_tour=?,
                latitude=?, longitude=?, description=?, last_seen=?
            WHERE source=? AND external_id=?
            """,
            (
                listing.price_php, listing.price_per_sqm, listing.title,
                listing.beds, listing.baths, listing.area_sqm,
                listing.location_text, listing.province, listing.zone_id,
                json.dumps(listing.amenities), json.dumps(listing.images),
                listing.agent, int(listing.is_featured),
                int(listing.has_virtual_tour), listing.latitude,
                listing.longitude, listing.description, now,
                listing.source, listing.external_id,
            ),
        )

        if price_changed:
            self._record_price(listing, now)
            return "price_change", listing.price_php - old_price

        return "unchanged", None

    def _record_price(self, listing: Listing, now: str) -> None:
        self.conn.execute(
            "INSERT INTO price_history (source, external_id, price_php, seen_at) "
            "VALUES (?,?,?,?)",
            (listing.source, listing.external_id, listing.price_php, now),
        )

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
