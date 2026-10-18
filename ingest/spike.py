"""Data spike: how much real hours / price data does OSM have for each city?

Usage:
    python -m ingest.spike "<city A>" "<city B>" "<city C>" [--osrm-url http://localhost:5000]
    python -m ingest.spike "Rome, Italy@41.87,12.43,41.94,12.53" "Lisbon, Portugal"

A city may carry its own area after an @ (south,west,north,east). Without it the geocoded
city boundary is used.

Numbers are measured on raw OSM only (no manual curation), so they describe data coverage.
Writes docs/data-spike.md and docs/data-spike.json, even if a city fails.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from .geocode import parse_bbox
from .matrix import osrm_sample, summarize_osrm
from .pipeline import run_city

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}%" if d else "n/a"


def parse_city_arg(text: str) -> tuple[str, tuple | None]:
    """'Rome, Italy@41.87,12.43,41.94,12.53' -> ('Rome, Italy', (41.87, 12.43, 41.94, 12.53))."""
    if "@" not in text:
        return text.strip(), None
    name, bbox = text.rsplit("@", 1)
    return name.strip(), parse_bbox(bbox)


# What a traveler plans a day around. Restaurants, cafes and bars are left out of the
# "top sights" view because they outnumber the sights twenty to one.
_FOOD_AND_DRINK = {"restaurant", "cafe", "bakery", "bar", "nightclub"}
TOP_SIGHTS = 100


def _coverage(places: list[dict]) -> dict:
    return {
        "n": len(places),
        "hours_known": sum(p["hours"]["confidence"] == "known" for p in places),
        "price_known": sum(p["cost"]["confidence"] == "known" for p in places),
    }


def city_stats(places: list[dict], report: dict) -> dict:
    n = len(places)
    hs = report["hours_status"]
    paid = sum(1 for p in places if p["cost"]["confidence"] == "known" and p["cost"]["amount"] > 0)
    free = sum(1 for p in places if p["cost"]["confidence"] == "known" and p["cost"]["amount"] == 0)
    assumed_free = sum(1 for p in places if p["cost"]["confidence"] == "inferred")
    sights = sorted(
        (p for p in places if p["categories"][0] not in _FOOD_AND_DRINK),
        key=lambda p: (-p.get("popularity", 0.0), p["id"]),
    )[:TOP_SIGHTS]
    by_cat: dict[str, dict] = defaultdict(lambda: {"n": 0, "hours_known": 0, "price_known": 0})

    for p in places:
        c = by_cat[p["categories"][0]]
        c["n"] += 1
        c["hours_known"] += p["hours"]["confidence"] == "known"
        c["price_known"] += p["cost"]["confidence"] == "known"

    return {
        "places": n,
        "hours_parsed": hs.get("parsed", 0),
        "hours_unparseable": hs.get("unparseable", 0),
        "hours_absent": hs.get("absent", 0),
        "price_known_paid": paid,
        "price_known_free": free,
        "price_assumed_free": assumed_free,
        "price_no_data": n - paid - free - assumed_free,
        "top_sights": _coverage(sights),
        "dropped": {k: v for k, v in report["counts"].items() if k.startswith("dropped_")},
        "duplicates_merged": report.get("duplicates", {}).get("merged", 0),
        "bbox": report.get("bbox"),
        "bbox_source": report.get("bbox_source", "geocoded"),
        "by_category": dict(by_cat),
    }


def render(results: dict, today: str) -> str:
    lines = [
        "# Data spike: OSM coverage of hours and prices",
        "",
        f"Generated {today} by `python -m ingest.spike`. Raw OSM only, no manual curation.",
        "",
        "- **Real hours**: `opening_hours` present and fully parsed (confidence `known`).",
        "- **Unparseable**: tag present but outside the supported subset (confidence `unknown`).",
        "- **No hours tag**: category default used (confidence `inferred`).",
        "- **Real price**: `charge` parsed to one amount (`known`, > 0).",
        "- **Known free**: `fee=no` (`known`).",
        "- **Assumed free**: no fee tag on a usually free category such as a park or a church "
        "(`inferred`).",
        "",
        "## Summary",
        "",
        (
            "| City | Status | Places | Real hours | Unparseable | "
            "No hours tag | Real price | Known free | Assumed free | No price data |"
        ),
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for city, result in results.items():
        if result.get("error"):
            lines.append(f"| {city} | FAILED | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
            continue

        stats = result["stats"]
        n = stats["places"]
        lines.append(
            f"| {city} | OK | {n} | "
            f"{_pct(stats['hours_parsed'], n)} | "
            f"{_pct(stats['hours_unparseable'], n)} | "
            f"{_pct(stats['hours_absent'], n)} | "
            f"{_pct(stats['price_known_paid'], n)} | "
            f"{_pct(stats['price_known_free'], n)} | "
            f"{_pct(stats.get('price_assumed_free', 0), n)} | "
            f"{_pct(stats['price_no_data'], n)} |"
        )

    ok = {city: r["stats"] for city, r in results.items() if not r.get("error")}
    if ok:
        lines += [
            "",
            f"## The {TOP_SIGHTS} most popular sights per city",
            "",
            "Food and drink left out. These are the places an itinerary is built around, so "
            "this is the coverage that matters most.",
            "",
            "| City | Sights | Real hours | Real price or known free |",
            "|---|---:|---:|---:|",
        ]
        for city, stats in ok.items():
            top = stats.get("top_sights") or {"n": 0, "hours_known": 0, "price_known": 0}
            lines.append(
                f"| {city} | {top['n']} | {_pct(top['hours_known'], top['n'])} | "
                f"{_pct(top['price_known'], top['n'])} |"
            )

    for city, result in results.items():
        if result.get("error"):
            lines += ["", f"## {city}", "", f"**Failed:** {result['error']}"]
            continue

        stats = result["stats"]
        lines += [
            "",
            f"## {city}",
            "",
            "| Primary category | Places | Real hours | Real price or known free |",
            "|---|---|---|---|",
        ]

        for category, counts in sorted(
            stats["by_category"].items(),
            key=lambda item: -item[1]["n"],
        ):
            lines.append(
                f"| {category} | {counts['n']} | "
                f"{_pct(counts['hours_known'], counts['n'])} | "
                f"{_pct(counts['price_known'], counts['n'])} |"
            )

        if stats["dropped"]:
            dropped = ", ".join(
                f"{key[8:]}={value}" for key, value in sorted(stats["dropped"].items())
            )
            lines += ["", "Dropped: " + dropped]

        if stats.get("duplicates_merged"):
            lines += ["", f"Duplicate records merged: {stats['duplicates_merged']}"]

        if stats.get("bbox"):
            area = ", ".join(f"{v:.4f}" for v in stats["bbox"])
            lines += ["", f"Area ({stats.get('bbox_source', 'geocoded')} bbox, S,W,N,E): {area}"]

        if result.get("osrm"):
            osrm = result["osrm"]
            lines += [
                "",
                (
                    f"Routing check (OSRM sample, "
                    f"{osrm.get('n_pairs', 0)} pairs): "
                    f"{osrm.get('note', '')}"
                ),
            ]

            if "median_ratio" in osrm:
                lines.append(
                    f"Median ratio {osrm['median_ratio']}, "
                    f"mean {osrm['mean_ratio']}, p90 {osrm['p90_ratio']}."
                )

    lines += [
        "",
        "## Reading these numbers",
        "",
        "- Coverage differs by category (museums vs. restaurants),",
        "  so compare the per-category tables.",
        "- `typical_duration_minutes` is always a category default "
        "(the contract has no confidence field for it).",
        "- Holiday (`PH`/`SH`) opening rules are ignored; the contract has no holiday field.",
    ]
    lines += _decision(ok)

    return "\n".join(lines) + "\n"


def _decision(ok: dict) -> list[str]:
    """Plain conclusions computed from the numbers, so they stay true when the data changes."""
    if not ok:
        return []

    def share(stats, key):
        return 100 * stats[key] / stats["places"] if stats["places"] else 0.0

    hours = [share(s, "hours_parsed") for s in ok.values()]
    priced = [share(s, "price_known_paid") + share(s, "price_known_free") for s in ok.values()]
    top_hours = [
        100 * s["top_sights"]["hours_known"] / s["top_sights"]["n"]
        for s in ok.values()
        if s.get("top_sights", {}).get("n")
    ]
    lines = [
        "",
        "## What this means",
        "",
        f"- Real opening hours exist for {min(hours):.0f} to {max(hours):.0f}% of places. "
        "The optimizer has to plan most stops on `inferred` hours, as a soft constraint, and "
        "the UI has to say so.",
        f"- A known price (paid or free) exists for {min(priced):.1f} to {max(priced):.1f}% of "
        "places. OSM is not a price source; budget totals rest on curation and category "
        "assumptions.",
    ]
    if top_hours:
        lines.append(
            f"- Among the {TOP_SIGHTS} most popular sights, {min(top_hours):.0f} to "
            f"{max(top_hours):.0f}% have real hours. Hand curating the top sights of the demo "
            "city closes the gap where it matters, which is what data/curation/ does."
        )
    lines.append(
        "- Recommendation: for the MVP, curate the top sights of the demo city instead of "
        "wiring in a commercial places API. Revisit a free tier (restaurant hours and ratings) "
        "only when more cities are needed."
    )
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the data spike over several cities.")
    ap.add_argument("cities", nargs="+")
    ap.add_argument("--cache", default=str(REPO_ROOT / "data" / "cache"))
    ap.add_argument("--out", default=str(REPO_ROOT / "data" / "out"))
    ap.add_argument("--contracts", default=str(REPO_ROOT / "contracts"))
    ap.add_argument("--docs", default=str(REPO_ROOT / "docs"))
    ap.add_argument(
        "--osrm-url",
        help="self-hosted OSRM base URL for the routing comparison",
    )
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args(argv)

    results: dict = {}
    failures = 0

    for arg in args.cities:
        city, bbox = parse_city_arg(arg)
        try:
            res = run_city(
                city,
                cache_dir=Path(args.cache),
                out_dir=Path(args.out),
                contracts_dir=Path(args.contracts),
                refresh=args.refresh,
                bbox=bbox,
            )
            entry = {"stats": city_stats(res["places"], res["report"])}

            if args.osrm_url and len(res["places"]) >= 2:
                try:
                    sample, minutes = osrm_sample(res["places"], args.osrm_url)
                    entry["osrm"] = summarize_osrm(sample, minutes)
                except Exception as exc:
                    entry["osrm"] = {
                        "n_pairs": 0,
                        "note": f"OSRM unavailable: {exc}",
                    }

            results[city] = entry
            print(f"[{city}] completed successfully")

        except Exception as exc:
            failures += 1
            results[city] = {"error": f"{type(exc).__name__}: {exc}"}
            print(f"[{city}] failed: {exc}", file=sys.stderr)

    docs = Path(args.docs)
    docs.mkdir(parents=True, exist_ok=True)

    (docs / "data-spike.md").write_text(
        render(results, date.today().isoformat()),
        encoding="utf-8",
    )
    (docs / "data-spike.json").write_text(
        json.dumps(results, indent=1),
        encoding="utf-8",
    )

    print(f"wrote {docs / 'data-spike.md'}")
    print(f"wrote {docs / 'data-spike.json'}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
