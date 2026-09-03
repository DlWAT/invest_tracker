"""Bien'ici scraper (France).

Bien'ici is a French real-estate aggregator. Its search page is a JS SPA, but
the underlying JSON endpoints are server-accessible and do not require an API
key:

- search:  GET /realEstateAds.json?filters={...}
- detail:  GET /realEstateAd.json?id={id}

The search returns a rich, paginated list of ads (price, surface, type, city,
postal code, photos, blurred GPS position), enough to feed the app without a
detail request. :meth:`enrich` adds rooms/bedrooms/description/amenities.
"""

from __future__ import annotations

import json
import time

import requests

from ..config import (
    BASE_URL,
    DEFAULT_USER_AGENT,
    DEPARTMENTS_BY_SLUG,
    MAX_PAGES_PER_SEARCH,
    MAX_PRICE_EUR,
    MIN_PRICE_EUR,
    PROPERTY_TYPES,
    assign_zone,
)
from ph_scanner.models import Listing, normalize_type
from ph_scanner.sources.base import BaseSource

SEARCH_URL = BASE_URL + "/realEstateAds.json"
DETAIL_URL = BASE_URL + "/realEstateAd.json"

PAGE_SIZE = 100
# Bien'ici caps a search at ~2500 results; stop there to avoid an endless loop.
MAX_RESULTS = 2500


class BienIciSource(BaseSource):
    name = "bienici"
    types = PROPERTY_TYPES

    def __init__(self, timeout: int = 30, delay: float = 1.0,
                 min_price: int | None = MIN_PRICE_EUR,
                 max_price: int | None = MAX_PRICE_EUR):
        self.timeout = timeout
        self.delay = delay
        self.min_price = min_price
        self.max_price = max_price
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json",
            "Referer": "https://www.bienici.com/recherche/achat/",
        })

    def _get(self, url: str, params: dict) -> dict:
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _filters(self, zone_id: str, property_type: str, offset: int,
                 min_price: int | None, max_price: int | None) -> dict:
        f = {
            "size": PAGE_SIZE,
            "from": offset,
            "filterType": "buy",
            "zoneIdsByTypes": {"zoneIds": [zone_id]},
            "propertyType": [property_type],
            "sortBy": "publicationDate",
            "sortOrder": "desc",
        }
        if max_price:
            f["maxPrice"] = max_price
        if min_price:
            f["minPrice"] = min_price
        return f

    def search_all(self, department: str, property_type: str,
                   max_pages: int = MAX_PAGES_PER_SEARCH) -> list[Listing]:
        """Collect all sale listings for a department + property type."""
        dept = DEPARTMENTS_BY_SLUG.get(department)
        if dept is None:
            return []

        listings: list[Listing] = []
        offset = 0
        cap = min(MAX_RESULTS, max_pages * PAGE_SIZE)
        while offset < cap:
            data = self._get(
                SEARCH_URL,
                {"filters": json.dumps(self._filters(
                    dept["zone_id"], property_type, offset,
                    self.min_price, self.max_price,
                ))},
            )
            ads = data.get("realEstateAds") or []
            if not ads:
                break
            for ad in ads:
                listing = self._parse_ad(ad, department, property_type)
                if listing is not None:
                    listings.append(listing)
            if len(ads) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
            time.sleep(self.delay)

        return listings

    @staticmethod
    def _to_int(value) -> int | None:
        try:
            return int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    def _parse_ad(self, ad: dict, department: str, property_type: str) -> Listing | None:
        ad_id = ad.get("id")
        if not ad_id:
            return None

        price = self._to_int(ad.get("price"))
        area = ad.get("surfaceArea")
        area = self._to_int(area) if area is not None else None
        area = float(area) if area else None

        raw_type = ad.get("propertyType") or property_type
        ptype = "apartment" if raw_type == "flat" else normalize_type(raw_type)

        price_per_sqm = None
        if price and area:
            price_per_sqm = round(price / area, 2)

        photos = ad.get("photos") or []
        images = [p["url"] for p in photos if p.get("url")]

        position = (ad.get("blurInfo") or {}).get("position") or {}
        lat = position.get("lat")
        lon = position.get("lon") or position.get("lng")

        city = ad.get("city") or ""
        location_text = city
        if ad.get("postalCode"):
            location_text = f"{city} ({ad['postalCode']})" if city else ad["postalCode"]

        return Listing(
            source=self.name,
            external_id=ad_id,
            url=f"{BASE_URL}/annonce/{ad_id}",
            title=(ad.get("title") or "").strip(),
            price_php=price,
            price_per_sqm=price_per_sqm,
            beds=None,
            baths=None,
            area_sqm=area,
            property_type=ptype,
            location_text=location_text,
            province=department,
            zone_id=assign_zone(department, ad.get("title") or "", location_text),
            amenities=[],
            images=images,
            agent=None,
            latitude=float(lat) if lat is not None else None,
            longitude=float(lon) if lon is not None else None,
            description=(ad.get("description") or "").strip() or None,
        )

    def enrich(self, listing: Listing) -> Listing:
        """Fill rooms/bedrooms/baths/amenities/full description from detail."""
        try:
            data = self._get(DETAIL_URL, {"id": listing.external_id})
        except requests.RequestException:
            return listing

        listing.beds = self._to_int(data.get("bedroomsQuantity"))
        listing.baths = self._to_int(data.get("bathroomsQuantity"))
        if data.get("surfaceArea"):
            area = self._to_int(data.get("surfaceArea"))
            if area and area > 0:
                listing.area_sqm = float(area)
                if listing.price_php:
                    listing.price_per_sqm = round(listing.price_php / area, 2)
        if data.get("description"):
            listing.description = data["description"].strip()

        amenities = []
        for flag, label in (
            ("hasPool", "Piscine"),
            ("hasTerrace", "Terrasse"),
            ("hasGarden", "Jardin"),
            ("hasGarage", "Garage"),
            ("hasBalcony", "Balcon"),
            ("hasCellar", "Cave"),
        ):
            if data.get(flag):
                amenities.append(label)
        if amenities:
            listing.amenities = amenities

        time.sleep(self.delay)
        return listing
