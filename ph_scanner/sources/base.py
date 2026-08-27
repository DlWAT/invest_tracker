"""Base scraper interface."""

from __future__ import annotations

import abc

from ..models import Listing


class BaseSource(abc.ABC):
    name: str = "base"
    types: list[str] = []
    min_price: int | None = None
    max_price: int | None = None

    @abc.abstractmethod
    def search_all(self, province: str, property_type: str,
                   max_pages: int = 40) -> list[Listing]:
        """Collect all listings for a province + property type."""

    @abc.abstractmethod
    def enrich(self, listing: Listing) -> Listing:
        """Fetch and fill detail-page fields (gps, description, etc.)."""
