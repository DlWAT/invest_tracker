"""DotProperty.com.ph scraper.

Fetches the search results pages (server-rendered HTML) for a province +
property type and normalizes them into Listing objects. Detail-page
enrichment (GPS / full description) is available via :meth:`enrich`.
"""

from __future__ import annotations

import re
import time

import requests
from bs4 import BeautifulSoup

from ..config import (
    BASE_URL,
    DEFAULT_USER_AGENT,
    MAX_PAGES_PER_SEARCH,
    MAX_PRICE_PHP,
    MIN_PRICE_PHP,
    PROPERTY_TYPES,
    assign_zone,
)
from ..models import Listing, normalize_type, parse_area, parse_int, parse_price
from .base import BaseSource

IMG_MARKERS = {
    "bed": "bed",
    "bath": "bathtub",
    "area": "resize",
    "type": "home",
}


class DotPropertySource(BaseSource):
    name = "dotproperty"
    types = PROPERTY_TYPES

    def __init__(
        self,
        timeout: int = 30,
        delay: float = 1.0,
        min_price: int | None = MIN_PRICE_PHP,
        max_price: int | None = MAX_PRICE_PHP,
    ):
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

    def _search_url(self, property_type: str, province_slug: str, page: int,
                    min_price: int | None = None, max_price: int | None = None) -> str:
        lo = self.min_price if min_price is None else min_price
        hi = self.max_price if max_price is None else max_price
        params = [f"page={page}"]
        if hi:
            params.append(f"max_price={hi}")
        if lo:
            params.append(f"min_price={lo}")
        return (
            f"{BASE_URL}/{property_type}-for-sale/{province_slug}"
            f"?{'&'.join(params)}"
        )

    def search(self, province: str, property_type: str,
               max_pages: int = MAX_PAGES_PER_SEARCH,
               min_price: int | None = None,
               max_price: int | None = None) -> list[Listing]:
        """Fetch all pages for a province + property type (single price slice)."""
        listings: list[Listing] = []

        page = 1
        while page <= max_pages:
            url = self._search_url(property_type, province, page, min_price, max_price)
            html = self._get(url)
            soup = BeautifulSoup(html, "lxml")

            cards = soup.select("article.listing-snippet")
            if not cards:
                break

            for card in cards:
                listing = self._parse_card(card, province, property_type)
                if listing is not None:
                    listings.append(listing)

            # Stop early when the last page is reached (fewer than a full page).
            if len(cards) < 25:
                break

            page += 1
            time.sleep(self.delay)

        return listings

    def search_all(self, province: str, property_type: str,
                   max_pages: int = MAX_PAGES_PER_SEARCH) -> list[Listing]:
        """Search a province+type, subdividing by price when the result
        count exceeds the pagination cap (avoids silent truncation at ~1000)."""
        cap = max_pages * 25
        total = self._total_count(province, property_type)
        if total is None or total <= cap:
            return self.search(province, property_type, max_pages)
        return self._search_batched(province, property_type,
                                    self.min_price, self.max_price, max_pages, cap)

    def _search_batched(self, province: str, property_type: str,
                        lo: int | None, hi: int | None,
                        max_pages: int, cap: int) -> list[Listing]:
        n = self._total_count(province, property_type, lo, hi)
        if n is not None and n <= cap:
            return self.search(province, property_type, max_pages,
                               min_price=lo, max_price=hi)

        lo = lo if lo is not None else 0
        hi = hi if hi is not None else 50_000_000
        if hi - lo <= 100_000:
            # Floor: stop splitting, return whatever this slice holds.
            return self.search(province, property_type, max_pages,
                               min_price=lo, max_price=hi)

        mid = (lo + hi) // 2
        left = self._search_batched(province, property_type, lo, mid, max_pages, cap)
        time.sleep(self.delay)
        right = self._search_batched(province, property_type, mid + 1, hi, max_pages, cap)
        return left + right

    def _total_count(self, province: str, property_type: str,
                     min_price: int | None = None,
                     max_price: int | None = None) -> int | None:
        url = self._search_url(property_type, province, 1, min_price, max_price)
        html = self._get(url)
        m = re.search(r'id="properties_total">([\d,]+)<', html)
        if m:
            return int(m.group(1).replace(",", ""))
        return None

    def _parse_card(self, card, province: str, property_type: str) -> Listing | None:
        link = self._find_listing_link(card)
        if link is None:
            return None

        url = link["href"]
        if not url.startswith("http"):
            url = BASE_URL + url

        title_el = card.select_one("div.text-2xl")
        title = title_el.get_text(" ", strip=True) if title_el else None

        external_id = card.get("data-uuid") or self._extract_id_from_url(url)
        if external_id is None:
            return None

        price_php = parse_price(self._text(card, "div.text-secondary-base"))
        price_per_sqm = parse_price(self._price_per_sqm(card))

        beds = baths = area = None
        prop_type = property_type.rstrip("s")
        for li in card.select("ul li"):
            img = li.select_one("img")
            src = (img.get("src") or "") if img else ""
            text = li.get_text(" ", strip=True)
            if "bed" in src:
                beds = parse_int(text)
            elif "bathtub" in src:
                baths = parse_int(text)
            elif "resize" in src:
                area = parse_area(text)
            elif "home" in src:
                prop_type = text
        prop_type = normalize_type(prop_type)

        # Fallback: derive price/m2 from price and area when not displayed.
        if price_per_sqm is None and price_php and area:
            price_per_sqm = round(price_php / area, 2)

        location_text = self._location(card)
        zone_id = assign_zone(province, title or "", location_text or "")

        amenities = [
            li.get_text(" ", strip=True)
            for li in card.select("ul.facilities li")
            if not re.fullmatch(r"\+\d+", li.get_text(" ", strip=True))
        ]

        images = self._extract_images(card)

        agent = None
        agent_el = card.select_one("div[title] span.truncate")
        if agent_el is not None:
            agent = agent_el.get_text(" ", strip=True)

        text = card.get_text(" ", strip=True).lower()
        return Listing(
            source=self.name,
            external_id=external_id,
            url=url,
            title=title or "",
            price_php=price_php,
            price_per_sqm=price_per_sqm,
            beds=beds,
            baths=baths,
            area_sqm=area,
            property_type=prop_type,
            location_text=location_text or "",
            province=province,
            zone_id=zone_id,
            amenities=amenities,
            images=images,
            agent=agent,
            is_featured="featured" in text,
            has_virtual_tour="virtual tour" in text,
        )

    @staticmethod
    def _text(card, selector: str) -> str | None:
        el = card.select_one(selector)
        return el.get_text(" ", strip=True) if el else None

    @staticmethod
    def _price_per_sqm(card) -> str | None:
        for div in card.select("div.text-neutral-2"):
            txt = div.get_text(" ", strip=True)
            if "/ m" in txt or "/m" in txt:
                return txt
        return None

    @staticmethod
    def _location(card) -> str | None:
        for span in card.select("div span img[src*='location']"):
            parent = span.find_parent("div")
            if parent:
                return parent.get_text(" ", strip=True)
        return None

    @staticmethod
    def _extract_images(card) -> list[str]:
        """Collect unique property-photo CDN URLs from a listing card.

        DotProperty uses two CDNs:
        - pix.dotproperty.co.th  (regular listings, resized thumbnails)
        - images.proppit.com/properties/... (project/developer listings)
        Agent logos live under images.proppit.com/publisher/ and are excluded.
        """
        seen: set[str] = set()
        out: list[str] = []
        for img in card.select("img"):
            src = img.get("src") or img.get("data-src") or ""
            if "pix.dotproperty" in src or "images.proppit.com/properties/" in src:
                if src in seen:
                    continue
                seen.add(src)
                out.append(src)
        return out

    @staticmethod
    def _extract_id_from_url(url: str) -> str | None:
        m = re.search(r"_([0-9a-f]{8}-[0-9a-f\-]+|\d{5,})$", url)
        return m.group(1) if m else None

    @staticmethod
    def _find_listing_link(card):
        link = card.select_one("a[href*='/ads/']")
        if link is not None:
            return link
        for a in card.select("a[href]"):
            href = a["href"]
            if "agency" in href or "javascript:" in href:
                continue
            if re.search(r"_[0-9a-f]{8}-[0-9a-f\-]+$", href) or \
               re.search(r"_\d{5,}$", href):
                return a
        return None

    def enrich(self, listing: Listing) -> Listing:
        """Fetch detail page to fill GPS and full description."""
        try:
            html = self._get(listing.url)
        except requests.RequestException:
            return listing

        soup = BeautifulSoup(html, "lxml")
        lat = soup.select_one("meta[itemprop='latitude']")
        lng = soup.select_one("meta[itemprop='longitude']")
        if lat and lat.get("content"):
            listing.latitude = float(lat["content"])
        if lng and lng.get("content"):
            listing.longitude = float(lng["content"])

        desc_el = soup.select_one("div.add-padding .description, div[itemprop='description']")
        if desc_el is None:
            desc_el = soup.select_one("div[id='description'], div.description")
        if desc_el:
            listing.description = desc_el.get_text(" ", strip=True)

        time.sleep(self.delay)
        return listing
