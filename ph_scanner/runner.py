"""Command-line entry point that orchestrates collection."""

from __future__ import annotations

import argparse
import sys

from .config import (
    MAX_PRICE_PHP,
    MIN_PRICE_PHP,
    PROVINCES,
)
from .sources.dotproperty import DotPropertySource
from .sources.filipinohomes import FilipinoHomesSource
from .storage import Storage

SOURCES = {
    "dotproperty": DotPropertySource,
    "filipinohomes": FilipinoHomesSource,
}


def build_sources(source_names: list[str], delay: float,
                  min_price: int | None, max_price: int | None) -> list:
    return [
        SOURCES[name](delay=delay, min_price=min_price, max_price=max_price)
        for name in source_names
    ]


def collect(sources: list, storage: Storage, provinces: list[str],
            types: list[str] | None = None, enrich: bool = False,
            max_pages: int = 40, progress=print) -> dict:
    """Run the collection loop, reporting progress via ``progress(line)``.

    Returns the stats dict: ``{"new", "updated", "price_change", "unchanged"}``.
    """
    stats = {"new": 0, "updated": 0, "price_change": 0, "unchanged": 0}
    batch = 0
    for source in sources:
        stypes = [t for t in source.types if types is None or t in types]
        for province in provinces:
            for ptype in stypes:
                try:
                    listings = source.search_all(province, ptype, max_pages=max_pages)
                except Exception as exc:  # noqa: BLE001
                    progress(f"[!] {source.name}/{province}/{ptype}: {exc}")
                    continue

                for listing in listings:
                    if enrich:
                        listing = source.enrich(listing)
                    status, _diff = storage.upsert(listing)
                    stats[status] += 1
                    batch += 1
                    if batch % 200 == 0:
                        storage.commit()

                storage.commit()
                progress(
                    f"[ok] {source.name:13s} {province:22s} {ptype:8s} -> "
                    f"{len(listings):4d} listings ({storage.count()} total in db)"
                )
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Philippine Airbnb Investment Scanner - collection"
    )
    parser.add_argument("--db", default="data/listings.db")
    parser.add_argument("--sources", nargs="*", default=None,
                        choices=list(SOURCES), help="Sources to collect (default: all)")
    parser.add_argument("--provinces", nargs="*", default=None,
                        help="Province slugs to collect (default: all Philippines)")
    parser.add_argument("--types", nargs="*", default=None,
                        help="Property types (default: all types of each source)")
    parser.add_argument("--enrich", action="store_true",
                        help="Fetch detail pages for GPS + description (slower)")
    parser.add_argument("--max-pages", type=int, default=40)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--min-price", type=int, default=MIN_PRICE_PHP,
                        help="Prix minimum en PHP (defaut: 0)")
    parser.add_argument("--max-price", type=int, default=MAX_PRICE_PHP,
                        help="Prix maximum en PHP (defaut: 6 000 000)")
    args = parser.parse_args(argv)

    provinces = args.provinces or PROVINCES
    source_names = args.sources or list(SOURCES)

    sources = build_sources(source_names, args.delay, args.min_price, args.max_price)
    storage = Storage(args.db)

    try:
        stats = collect(
            sources, storage, provinces,
            types=args.types, enrich=args.enrich, max_pages=args.max_pages,
            progress=print,
        )
        print("\n=== Summary ===")
        print(f"  new:          {stats['new']}")
        print(f"  price_change: {stats['price_change']}")
        print(f"  updated:      {stats['updated']}")
        print(f"  unchanged:    {stats['unchanged']}")
        print(f"  total in db:  {storage.count()}")
        return 0
    finally:
        storage.close()


if __name__ == "__main__":
    sys.exit(main())
