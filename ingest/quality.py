"""Data quality report: what a traveler actually gets, city by city.

Usage:
    python -m ingest.quality "Hyderabad" "New York" "Tokyo" "Paris" "Cairo" "Sydney"

Each city is loaded exactly as the app loads it (a saved copy, or a live OpenStreetMap fetch
with descriptions and bus stops), then a sample two-day trip is planned with the sample
traveler in fixtures/. The report measures the stops in that plan, because those are what a
traveler sees, plus the city's whole place list for the walk to the nearest stop.

Delete data/live/<city> first to measure a fresh fetch, including how long it takes.
Writes docs/data-quality.md and docs/data-quality.json, even if a city fails.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import date, timedelta
from pathlib import Path

from . import catalog
from .cache import write_json, write_text

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PROFILE = REPO_ROOT / "fixtures" / "sample.profile.json"
NEAR_STOP_MIN = 5.0  # "a short walk to transit"


def _share(n: int, d: int) -> float | None:
    return round(n / d, 3) if d else None


def plan_stats(itinerary: dict) -> dict:
    """What the traveler sees in the plan: hours, prices, descriptions and photos per stop."""
    items = [i for day in itinerary["days"] for i in day["items"]]
    n = len(items)
    count = lambda pred: sum(1 for i in items if pred(i))  # noqa: E731
    rides = [i["travel_from_prev"] for i in items
             if (i.get("travel_from_prev") or {}).get("mode") == "transit"]
    return {
        "stops": n,
        "hours_verified": _share(count(lambda i: i.get("confidence") == "known"), n),
        "hours_estimated": _share(count(lambda i: i.get("confidence") == "inferred"), n),
        "hours_unknown": _share(
            count(lambda i: i.get("confidence") not in ("known", "inferred")), n),
        "price_real": _share(count(lambda i: i.get("cost_confidence") == "known"), n),
        "price_estimated": _share(count(lambda i: i.get("cost_confidence") == "inferred"), n),
        "price_unknown": _share(count(lambda i: i.get("cost_confidence") == "unknown"), n),
        "described": _share(count(lambda i: bool(i.get("description"))), n),
        "from_wikipedia": _share(count(lambda i: i.get("description_source") == "wikipedia"), n),
        "with_photo": _share(count(lambda i: bool(i.get("photo"))), n),
        "with_open_hours": _share(count(lambda i: bool(i.get("open_hours"))), n),
        "transit_rides": len(rides),
        "ride_walk_minutes": sorted(round(r.get("walk_minutes", 0)) for r in rides),
        "currency": itinerary["totals"]["currency"],
        "trip_walking_minutes": itinerary["totals"]["walking_minutes"],
    }


def city_stats(places: list[dict], stop_walks: dict[str, float]) -> dict:
    """The whole city: how many places, and how close they are to public transport."""
    walks = [stop_walks[p["id"]] for p in places if p["id"] in stop_walks]
    return {
        "places": len(places),
        "with_stop_walk": len(walks),
        "median_walk_to_stop": round(statistics.median(walks), 1) if walks else None,
        "near_a_stop": _share(sum(1 for w in walks if w <= NEAR_STOP_MIN), len(walks)),
    }


def measure(name: str, start: date, plan=None, load=catalog.load_city) -> dict:
    """Load one city as the app does, plan a two-day sample trip, and measure both."""
    if plan is None:
        from optimizer.scheduler import plan_itinerary as plan
    profile = json.loads(SAMPLE_PROFILE.read_text(encoding="utf-8"))
    began = time.monotonic()
    city = load(name)
    load_seconds = round(time.monotonic() - began, 1)
    itinerary = plan(
        profile=profile,
        destination={"name": name},
        start_date=start.isoformat(),
        end_date=(start + timedelta(days=1)).isoformat(),
    )
    ids = {p["id"] for p in city.places}
    walks = {pid: m for pid, m in catalog._STOP_WALKS.items() if pid in ids}
    return {
        "city": itinerary["destination"]["name"],
        "source": city.source,
        "load_seconds": load_seconds,
        **city_stats(city.places, walks),
        **plan_stats(itinerary),
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def render(results: dict, today: str) -> str:
    ok = {k: v for k, v in results.items() if "error" not in v}
    lines = [
        "# Data quality: what a traveler actually gets",
        "",
        f"Generated {today} by `python -m ingest.quality`. Each city is loaded the way the app "
        "loads it, then a sample two-day trip is planned for the sample traveler "
        "(`fixtures/sample.profile.json`). Plan columns describe the stops in that trip; the "
        "last columns describe every place in the city.",
        "",
        "- **Verified hours / price**: from the place's own OpenStreetMap listing (or Rome's "
        "hand-checked sources). **Estimated**: usual hours or a typical price for that kind of "
        "place, shown to the traveler as \"estimated\" and with ≈.",
        "- **Unknown** is what the traveler would see as \"unverified\" or \"Price unknown\".",
        "",
        "## In the planned trip",
        "",
        "| City | Stops | Hours verified | Hours estimated | Hours unknown | Real price or free "
        "| Price ≈ estimate | Price unknown | Described | From Wikipedia | Photo |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in ok.values():
        lines.append(
            f"| {r['city']} | {r['stops']} | {_pct(r['hours_verified'])} | "
            f"{_pct(r['hours_estimated'])} | {_pct(r['hours_unknown'])} | "
            f"{_pct(r['price_real'])} | "
            f"{_pct(r['price_estimated'])} | {_pct(r['price_unknown'])} | {_pct(r['described'])} | "
            f"{_pct(r['from_wikipedia'])} | {_pct(r['with_photo'])} |"
        )
    lines += [
        "",
        "## The city as a whole",
        "",
        "| City | Currency | Places | Loaded in | Median walk to a bus stop or station "
        f"| Places within {NEAR_STOP_MIN:.0f} min of one | Rides in the trip (walk min each) |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for r in ok.values():
        walk = "n/a" if r["median_walk_to_stop"] is None else f"{r['median_walk_to_stop']} min"
        rides = ", ".join(map(str, r["ride_walk_minutes"])) or "none"
        fresh = " (fresh fetch)" if r["load_seconds"] > 5 else " (saved)"
        loaded = f"{r['load_seconds']} s{fresh}"
        lines.append(
            f"| {r['city']} | {r['currency']} | {r['places']} | {loaded} | {walk} | "
            f"{_pct(r['near_a_stop'])} | {r['transit_rides']} ({rides}) |"
        )
    failed = {k: v for k, v in results.items() if "error" in v}
    if failed:
        lines += ["", "## Not measured", ""]
        lines += [f"- {k}: {v['error']}" for k, v in failed.items()]
    if ok:
        with_unknowns = [
            f"{r['city']} ({_pct(r['hours_unknown'])} of stops with unknown hours, "
            f"{_pct(r['price_unknown'])} with an unknown price)"
            for r in ok.values()
            if (r["hours_unknown"] or 0) > 0 or (r["price_unknown"] or 0) > 0
        ]
        if with_unknowns:
            summary_line = (
                f"- In {len(with_unknowns)} of {len(ok)} cities some planned stops have unknown "
                "hours or prices, shown to the traveler as \"unverified\" or \"Price unknown\": "
                + "; ".join(with_unknowns) + "."
            )
        else:
            summary_line = (
                f"- Across {len(ok)} cities, no planned stop has unknown hours or prices: every "
                "stop has a verified value or an estimate the traveler can see is one."
            )
        lines += [
            "",
            "## Reading it",
            "",
            summary_line,
            "- Saved cities from before descriptions and bus stops existed (Rome's committed "
            "snapshot) show 0% described and no walk-to-stop data; live cities fetched now "
            "have both.",
        ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Measure the data a traveler gets, city by city.")
    ap.add_argument("cities", nargs="+")
    ap.add_argument("--docs", default=str(REPO_ROOT / "docs"))
    ap.add_argument("--start", help="first trip day, YYYY-MM-DD (default: a week from today)")
    a = ap.parse_args(argv)
    start = date.fromisoformat(a.start) if a.start else date.today() + timedelta(days=7)
    results: dict[str, dict] = {}
    for name in a.cities:
        print(f"== {name}")
        try:
            results[name] = measure(name, start)
            r = results[name]
            print(f"   {r['city']}: {r['stops']} stops, {r['places']} places, "
                  f"{r['load_seconds']} s")
        except Exception as exc:  # one failing city must not lose the others
            results[name] = {"error": f"{type(exc).__name__}: {exc}"}
            print(f"   failed: {results[name]['error']}")
    docs = Path(a.docs)
    write_json(docs / "data-quality.json", results, indent=1)
    write_text(docs / "data-quality.md", render(results, date.today().isoformat()))
    print(f"wrote {docs / 'data-quality.md'}")
    return 0 if all("error" not in r for r in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
