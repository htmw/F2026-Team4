"""python -m ingest "<city name>" [options]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .geocode import GeocodeError, parse_bbox
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
    ap.add_argument("--bbox", help="override geocoded area: south,west,north,east")
    ap.add_argument("--matrix-top", type=int, default=300, help="places included in matrix.json")
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
            matrix_top=a.matrix_top,
            speed_kmh=a.speed_kmh,
            detour_factor=a.detour_factor,
        )
    except (GeocodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0
