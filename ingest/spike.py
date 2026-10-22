"""Data spike: how much real opening hours and price data does OpenStreetMap have for Lisbon?

Usage:
    make data-spike                  (same as: python -m ingest.spike)

It runs the pipeline on the raw OSM data, without the curation file, and writes the
numbers to docs/data-spike.md and docs/data-spike.json. Run it again whenever the data
changes, so the numbers in the docs stay true. Downloads are cached in data/cache.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from .cache import write_json, write_text
from .pipeline import run_city

REPO_ROOT = Path(__file__).resolve().parents[1]
CITY = "Lisbon, Portugal"

# What a traveler plans a day around. Restaurants, cafes and bars are left out of the top
# sights view because they outnumber the sights twenty to one.
_FOOD_AND_DRINK = {"restaurant", "cafe", "bakery", "bar", "nightclub"}
TOP_SIGHTS = 100


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}%" if d else "n/a"


def city_stats(places: list[dict], report: dict) -> dict:
    """Coverage numbers for one pipeline run: counts by hours and price label."""
    n = len(places)
    hours = report["hours_status"]
    paid = sum(1 for p in places if p["cost"]["confidence"] == "known" and p["cost"]["amount"] > 0)
    free = sum(1 for p in places if p["cost"]["confidence"] == "known" and p["cost"]["amount"] == 0)
    assumed_free = sum(1 for p in places if p["cost"]["confidence"] == "inferred")
    sights = sorted(
        (p for p in places if p["categories"][0] not in _FOOD_AND_DRINK),
        key=lambda p: (-p.get("popularity", 0.0), p["id"]),
    )[:TOP_SIGHTS]
    by_category: dict[str, dict] = defaultdict(lambda: {"n": 0, "hours_known": 0, "price_known": 0})
    for p in places:
        c = by_category[p["categories"][0]]
        c["n"] += 1
        c["hours_known"] += p["hours"]["confidence"] == "known"
        c["price_known"] += p["cost"]["confidence"] == "known"

    return {
        "places": n,
        "hours_parsed": hours.get("parsed", 0),
        "hours_unparseable": hours.get("unparseable", 0),
        "hours_absent": hours.get("absent", 0),
        "price_known_paid": paid,
        "price_known_free": free,
        "price_assumed_free": assumed_free,
        "price_no_data": n - paid - free - assumed_free,
        "top_sights": {
            "n": len(sights),
            "hours_known": sum(p["hours"]["confidence"] == "known" for p in sights),
            "price_known": sum(p["cost"]["confidence"] == "known" for p in sights),
        },
        "dropped": {k: v for k, v in report["counts"].items() if k.startswith("dropped_")},
        "duplicates_merged": report.get("duplicates", {}).get("merged", 0),
        "bbox": report.get("bbox"),
        "by_category": dict(by_category),
    }


def render(city: str, stats: dict, today: str) -> str:
    """The markdown report for docs/data-spike.md."""
    n = stats["places"]
    top = stats["top_sights"]
    rows = [
        ("All places", n),
        ("Real hours: opening_hours tag fully read (`known`)", stats["hours_parsed"]),
        ("Hours tag we cannot read (`unknown`)", stats["hours_unparseable"]),
        ("No hours tag: category default used (`inferred`)", stats["hours_absent"]),
        ("Real price: a charge tag with one amount (`known`)", stats["price_known_paid"]),
        ("Known free: fee=no (`known`)", stats["price_known_free"]),
        ("Assumed free: no fee tag on a usually free category (`inferred`)",
         stats["price_assumed_free"]),
        ("No price data (`unknown`)", stats["price_no_data"]),
    ]
    lines = [
        f"# Data spike: OSM coverage of opening hours and prices in {city}",
        "",
        f"Generated {today} by `python -m ingest.spike` (`make data-spike`). Raw OpenStreetMap "
        "data only, without the hand checked curation file.",
        "",
        "## Summary",
        "",
        "| What | Places | Share |",
        "|---|---:|---:|",
        *(f"| {label} | {count} | {_pct(count, n)} |" for label, count in rows),
        "",
        f"## The {TOP_SIGHTS} most popular sights",
        "",
        "Food and drink left out. An itinerary is built around these places, so this is the "
        "coverage that matters most.",
        "",
        f"- Real hours: {top['hours_known']} of {top['n']} ({_pct(top['hours_known'], top['n'])})",
        f"- Real price or known free: {top['price_known']} of {top['n']} "
        f"({_pct(top['price_known'], top['n'])})",
        "",
        "## By primary category",
        "",
        "| Primary category | Places | Real hours | Real price or known free |",
        "|---|---:|---:|---:|",
    ]
    for category, c in sorted(stats["by_category"].items(), key=lambda item: -item[1]["n"]):
        lines.append(
            f"| {category} | {c['n']} | {_pct(c['hours_known'], c['n'])} | "
            f"{_pct(c['price_known'], c['n'])} |"
        )
    dropped = ", ".join(
        f"{key.removeprefix('dropped_')}={count}" for key, count in sorted(stats["dropped"].items())
    )
    area = ", ".join(f"{v:.4f}" for v in stats["bbox"] or [])
    lines += [
        "",
        f"Dropped records: {dropped or 'none'}. Duplicate records merged: "
        f"{stats['duplicates_merged']}. Area searched (south, west, north, east): {area}.",
        "",
        "## What this means",
        "",
        f"- Real opening hours exist for {_pct(stats['hours_parsed'], n)} of places. The "
        "optimizer has to plan most stops on `inferred` hours, as a soft constraint, and the "
        "app has to say so.",
        f"- A known price (paid or free) exists for "
        f"{_pct(stats['price_known_paid'] + stats['price_known_free'], n)} of places. "
        "OpenStreetMap is not a price source, so budget totals rest on the curation file and "
        "on category defaults.",
        f"- Among the {TOP_SIGHTS} most popular sights, {_pct(top['hours_known'], top['n'])} have "
        "real hours. Hand checking those sights on their official websites, in a curation file "
        "(data/curation/lisbon.json, not written yet), closes the gap where it matters most.",
        "- `typical_duration_minutes` is always a category default unless a curated entry sets "
        "it. Holiday rules (PH, SH) are skipped because the contract has no holiday field.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=f"Measure OSM hours and price coverage for {CITY}.")
    ap.add_argument("--cache", default=str(REPO_ROOT / "data" / "cache"))
    ap.add_argument("--out", default=str(REPO_ROOT / "data" / "out"))
    ap.add_argument("--contracts", default=str(REPO_ROOT / "contracts"))
    ap.add_argument("--docs", default=str(REPO_ROOT / "docs"))
    ap.add_argument("--refresh", action="store_true", help="download again, ignore the cache")
    args = ap.parse_args(argv)

    try:
        result = run_city(
            CITY,
            cache_dir=Path(args.cache),
            out_dir=Path(args.out),
            contracts_dir=Path(args.contracts),
            refresh=args.refresh,
        )
    except Exception as exc:
        # Keep the last good report rather than overwrite it with a failure.
        print(f"error: the {CITY} run failed, docs left as they were: {exc}", file=sys.stderr)
        return 1

    stats = city_stats(result["places"], result["report"])
    docs = Path(args.docs)
    write_text(docs / "data-spike.md", render(CITY, stats, date.today().isoformat()))
    write_json(docs / "data-spike.json", {"city": CITY, "stats": stats}, indent=1)
    print(f"wrote {docs / 'data-spike.md'} and {docs / 'data-spike.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
