"""FilipinoHomes.com scraper.

Server-rendered (MUI/Next.js) property portal. Complementary to DotProperty:
more direct-owner / developer listings, plus sub-types (beach-house, resort,
townhouse, boarding-house) that fit the Airbnb use case.

List URL:  /for-sale/{type}/in-{province}-philippines[/page/{n}]
Detail URL: /{slug}
"""

from __future__ import annotations

import html as html_lib
import re
import time

import requests
from bs4 import BeautifulSoup

from ..config import DEFAULT_USER_AGENT, MAX_PRICE_PHP, MIN_PRICE_PHP, assign_zone
from ..models import Listing, normalize_type, parse_area, parse_int, parse_price
from .base import BaseSource

BASE = "https://filipinohomes.com"

# FilipinoHomes type segments -> canonical. Only these exist on the site.
TYPES = ["house", "condominium", "land", "commercial"]

PAGE_SIZE = 12

CODE_RE = re.compile(r"\b[A-Z]{2,6}-\d+\b")


class FilipinoHomesSource(BaseSource):
    name = "filipinohomes"
    types = TYPES

    def __init__(self, timeout: int = 30, delay: float = 1.0,
                 min_price: int | None = MIN_PRICE_PHP,
                 max_price: int | None = MAX_PRICE_PHP):
        self.timeout = timeout
        self.delay = delay
        self.min_price = min_price
        self.max_price = max_price
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": DEFAULT_USER_AGENT})

    def _get(self, url: str) -> str:
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.text

    def _list_url(self, property_type: str, province: str, page: int) -> str:
        url = f"{BASE}/for-sale/{property_type}/in-{province}-philippines"
        if page > 1:
            url += f"/page/{page}"
        return url

    def search_all(self, province: str, property_type: str,
                   max_pages: int = 40) -> list[Listing]:
        listings: list[Listing] = []
        page = 1
        while page <= max_pages:
            html = self._get(self._list_url(property_type, province, page))
            cards = self._cards(html)
            if not cards:
                break
            for card in cards:
                listing = self._parse_card(card, province, property_type)
                if listing is None:
                    continue
                if self.min_price and listing.price_php and listing.price_php < self.min_price:
                    continue
                if self.max_price and listing.price_php and listing.price_php > self.max_price:
                    continue
                listings.append(listing)
            if len(cards) < PAGE_SIZE:
                break
            page += 1
            time.sleep(self.delay)
        return listings

    @staticmethod
    def _cards(html: str):
        soup = BeautifulSoup(html, "lxml")
        return soup.select('a[class*="MuiCard-root"]')

    def _parse_card(self, card, province: str, property_type: str) -> Listing | None:
        href = card.get("href")
        if not href or href.startswith(("http://", "javascript:")):
            return None
        url = href if href.startswith("http") else BASE + href

        img = card.select_one("img.pc-image")
        images = [img["src"]] if img and img.get("src") else []
        title = img.get("alt") if img else None

        price_el = card.select_one("p.MuiTypography-h5")
        price = parse_price(price_el.get_text(" ", strip=True)) if price_el else None

        def aria(label: str) -> str | None:
            el = card.select_one(f'[aria-label="{label}"]')
            return el.get_text(" ", strip=True) if el else None

        beds = parse_int(aria("Bedrooms"))
        baths = parse_int(aria("Bathrooms"))
        floor = parse_area(aria("Floor Area"))
        land = parse_area(aria("Land Size"))
        area = floor if floor else land

        external_id = href.strip("/")
        code_el = card.select_one('[aria-label="Copy listing code"]')
        if code_el is not None and code_el.parent is not None:
            m = CODE_RE.search(code_el.parent.get_text(" ", strip=True))
            if m:
                external_id = m.group(0)

        loc_el = card.select_one('[aria-label*="Philippines"]')
        location_text = loc_el.get("aria-label") if loc_el else None

        price_per_sqm = None
        if price and area:
            price_per_sqm = round(price / area, 2)

        return Listing(
            source=self.name,
            external_id=external_id,
            url=url,
            title=title or "",
            price_php=price,
            price_per_sqm=price_per_sqm,
            beds=beds,
            baths=baths,
            area_sqm=area,
            property_type=normalize_type(property_type),
            location_text=location_text or "",
            province=province,
            zone_id=assign_zone(province, title or "", location_text or ""),
            amenities=[],
            images=images,
            agent=None,
        )

    def enrich(self, listing: Listing) -> Listing:
        """Fill GPS + description + extra images from the detail page."""
        try:
            html = self._get(listing.url)
        except requests.RequestException:
            return listing

        m = re.search(r'"geo_coordinates":\s*\{\s*"lat":([-\d.]+),\s*"lng":([-\d.]+)\}',
                      html)
        if not m:
            m = re.search(r'"latitude":([-\d.]+),\s*"longitude":([-\d.]+)', html)
        if m:
            listing.latitude = float(m.group(1))
            listing.longitude = float(m.group(2))

        # Gallery images from the schema.org "image" array.
        extra = re.findall(r'"url":"(https://filipinohomes123[^"]+\.webp)"', html)
        if extra:
            seen = set(listing.images)
            for u in extra:
                if u not in seen:
                    seen.add(u)
                    listing.images.append(u)

        # Description block after "Property Description".
        dm = re.search(r'Property Description\s*(.{0,1500})', html, re.S)
        if dm:
            listing.description = re.sub(r"<[^>]+>", " ", dm.group(1))
            listing.description = re.sub(r"\s+", " ", listing.description).strip()
            listing.description = html_lib.unescape(listing.description)

        time.sleep(self.delay)
        return listing
