"""Listing data model and price parsing helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict


def parse_price(value: str | None) -> int | None:
    """Parse a PHP price string like '₱ 4,286,528' into an int."""
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    if not digits:
        return None
    return int(digits)


def parse_area(value: str | None) -> float | None:
    """Parse an area like '179.25 m2', '324 sqm' or '1069 sq m' into a float."""
    if not value:
        return None
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*)?m", value, re.I)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


_TYPE_ALIASES = {
    "condo": "condo",
    "condominium": "condo",
    "house": "house",
    "villa": "villa",
    "hotel": "hotel",
    "resort": "hotel",
    "apartment": "apartment",
    "townhouse": "townhouse",
    "land": "land",
    "lot": "land",
}


def normalize_type(value: str | None) -> str:
    """Map a free-text property type to a canonical slug."""
    if not value:
        return "other"
    key = value.lower().strip()
    for token, canonical in _TYPE_ALIASES.items():
        if token in key:
            return canonical
    return key


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"\d+", value)
    return int(m.group(0)) if m else None


@dataclass
class Listing:
    """A normalized real-estate listing from any source."""

    source: str
    external_id: str
    url: str
    title: str
    price_php: int | None
    price_per_sqm: float | None
    beds: int | None
    baths: int | None
    area_sqm: float | None
    property_type: str
    location_text: str
    province: str | None
    zone_id: str | None
    amenities: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    agent: str | None = None
    is_featured: bool = False
    has_virtual_tour: bool = False
    # Detail-page enrichment (optional)
    latitude: float | None = None
    longitude: float | None = None
    description: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)
