"""Command line entry point: python -m ingest "<city name>" [options]

Examples:
    python -m ingest "Lisbon, Portugal"          # scratch run into data/out/lisbon-portugal
    python -m ingest "Lisbon, Portugal" --slug lisbon --alias Lisboa \\
        --alias "Lisboa, Portugal" --out data/cities   # the committed snapshot

Most people never call this directly: make snapshot-lisbon runs the second example.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .curation import CurationError
from .geocode import DEFAULT_MAX_SPAN_KM, GeocodeError, parse_bbox
from .overpass import GROUPS
from .pipeline import run_city

REPO_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="ingest", description="Fetch OpenStreetMap data for a city and build its places."
    )
    ap.add_argument("city", help='city name, e.g. "Lisbon, Portugal"')
    ap.add_argument("--cache", default=str(REPO_ROOT / "data" / "cache"))
    ap.add_argument("--out", default=str(REPO_ROOT / "data" / "out"))
    ap.add_argument("--contracts", default=str(REPO_ROOT / "contracts"))
    ap.add_argument("--refresh", action="store_true", help="ignore cached responses")
    ap.add_argument("--only", choices=list(GROUPS), action="append", help="limit to query group(s)")
    ap.add_argument(
        "--bbox",
        help="area to fetch: south,west,north,east. Skips the city size check.",
    )
    ap.add_argument(
        "--max-span-km",
        type=float,
        default=DEFAULT_MAX_SPAN_KM,
        help="largest geocoded area accepted without --bbox (default %(default)s km)",
    )
    ap.add_argument("--slug", help="output folder name, e.g. lisbon (default: from the city name)")
    ap.add_argument("--alias", action="append", default=[], help="extra name the API accepts")
    ap.add_argument(
        "--curation", help="hand checked facts to apply, e.g. data/curation/lisbon.json"
    )
    a = ap.parse_args(argv)
    try:
        run_city(
            a.city,
            cache_dir=Path(a.cache),
            out_dir=Path(a.out),
            contracts_dir=Path(a.contracts),
            refresh=a.refresh,
            groups=a.only,
            bbox=parse_bbox(a.bbox) if a.bbox else None,
            max_span_km=a.max_span_km,
            slug=a.slug,
            aliases=a.alias,
            curation_path=Path(a.curation) if a.curation else None,
        )
    except (GeocodeError, CurationError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0
