"""Data spike: how much real hours / price data does OSM have for each city?

    python -m ingest.spike "<city A>" "<city B>" "<city C>" [--osrm-url http://localhost:5000]

Numbers are measured on raw OSM only (no manual curation), so they describe data coverage.
Writes docs/data-spike.md and docs/data-spike.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from .matrix import osrm_sample, summarize_osrm
from .pipeline import run_city

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}%" if d else "n/a"


def city_stats(places: list[dict], report: dict) -> dict:
    n = len(places)
    hs = report["hours_status"]
    paid = sum(1 for p in places if p["cost"]["confidence"] == "known" and p["cost"]["amount"] > 0)
    free = sum(1 for p in places if p["cost"]["confidence"] == "known" and p["cost"]["amount"] == 0)
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
        "price_no_data": n - paid - free,
        "dropped": {k: v for k, v in report["counts"].items() if k.startswith("dropped_")},
        "by_category": dict(by_cat),
    }


def render(results: dict, today: str) -> str:
    lines = [
        "# Data spike: OSM coverage of hours and prices",
        "",
        (f"Generated {today} by `python -m ingest.spike`. Raw OSM only, no manual curation."),
        "",
        "- **Real hours**: `opening_hours` present and fully parsed (confidence `known`).",
        "- **Unparseable**: tag present but outside the supported subset (confidence `unknown`).",
        "- **No hours tag**: category default used (confidence `inferred`).",
        "- **Real price**: `charge` parsed to one amount (`known`, > 0).",
        "- **Known free**: `fee=no` (`known`).",
        "",
        "## Summary",
        "",
        (
            "| City | Places | Real hours | Unparseable | No hours tag | "
            "Real price | Known free | No price data |"
        ),
        "|---|---|---|---|---|---|---|---|",
    ]

    for city, result in results.items():
        stats = result["stats"]
        n = stats["places"]
        lines.append(
            f"| {city} | {n} | "
            f"{_pct(stats['hours_parsed'], n)} | "
            f"{_pct(stats['hours_unparseable'], n)} | "
            f"{_pct(stats['hours_absent'], n)} | "
            f"{_pct(stats['price_known_paid'], n)} | "
            f"{_pct(stats['price_known_free'], n)} | "
            f"{_pct(stats['price_no_data'], n)} |"
        )

    for city, result in results.items():
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
        (
            "- `typical_duration_minutes` is always a category default "
            "(the contract has no confidence field for it)."
        ),
        ("- Holiday (`PH`/`SH`) opening rules are ignored; the contract has no holiday field."),
    ]

    return "\n".join(lines) + "\n"


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

    for city in args.cities:
        res = run_city(
            city,
            cache_dir=Path(args.cache),
            out_dir=Path(args.out),
            contracts_dir=Path(args.contracts),
            refresh=args.refresh,
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
