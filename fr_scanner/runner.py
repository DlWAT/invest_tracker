"""Command-line entry point for the French collection.

Reuses the generic collection loop from ``ph_scanner.runner``, but with the
Bien'ici source and the French departments/budget.
"""

from __future__ import annotations

import argparse
import sys

from .config import MAX_PRICE_EUR, MIN_PRICE_EUR, PROVINCES
from .sources.bienici import BienIciSource
from ph_scanner.runner import collect
from ph_scanner.storage import Storage

SOURCES = {
    "bienici": BienIciSource,
}


def build_sources(source_names: list[str], delay: float,
                  min_price: int | None, max_price: int | None) -> list:
    return [
        SOURCES[name](delay=delay, min_price=min_price, max_price=max_price)
        for name in source_names
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="French Airbnb Investment Scanner - collection"
    )
    parser.add_argument("--db", default="data/listings_fr.db")
    parser.add_argument("--sources", nargs="*", default=None,
                        choices=list(SOURCES), help="Sources to collect (default: all)")
    parser.add_argument("--departments", nargs="*", default=None,
                        help="Department slugs to collect (default: all)")
    parser.add_argument("--types", nargs="*", default=None,
                        help="Property types (default: all types of each source)")
    parser.add_argument("--enrich", action="store_true",
                        help="Fetch detail pages for rooms + description (slower)")
    parser.add_argument("--max-pages", type=int, default=40)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--min-price", type=int, default=MIN_PRICE_EUR,
                        help="Prix minimum en EUR (defaut: 0)")
    parser.add_argument("--max-price", type=int, default=MAX_PRICE_EUR,
                        help="Prix maximum en EUR (defaut: 500 000)")
    args = parser.parse_args(argv)

    provinces = args.departments or PROVINCES
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
