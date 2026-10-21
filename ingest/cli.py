"""python -m ingest "<city name>" [options]

Examples:
    python -m ingest "Lisbon, Portugal"
    python -m ingest "London, UK" --bbox 51.45,-0.25,51.56,0.02
    python -m ingest "Rome, Italy" --bbox 41.87,12.43,41.94,12.53 --slug rome \\
        --alias Roma --out data/cities --curation data/curation/rome.json --matrix-top 0
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
        prog="ingest", description="Fetch and build Place[] for any destination."
    )
    ap.add_argument("city", help='destination name, e.g. "Kyoto" or "Cordoba, Argentina"')
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
    ap.add_argument("--slug", help="output folder name, e.g. rome (default: from the city name)")
    ap.add_argument("--alias", action="append", default=[], help="extra name the API accepts")
    ap.add_argument("--curation", help="hand checked facts to apply, e.g. data/curation/rome.json")
    ap.add_argument(
        "--matrix-top",
        type=int,
        default=300,
        help="places included in matrix.json, 0 writes no matrix file",
    )
    ap.add_argument("--speed-kmh", type=float, default=4.5)
    ap.add_argument("--detour-factor", type=float, default=1.3)
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
            matrix_top=a.matrix_top,
            speed_kmh=a.speed_kmh,
            detour_factor=a.detour_factor,
            slug=a.slug,
            aliases=a.alias,
            curation_path=Path(a.curation) if a.curation else None,
        )
    except (GeocodeError, CurationError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0
