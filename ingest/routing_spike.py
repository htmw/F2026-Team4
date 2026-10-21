"""Routing spike: how far is straight line x detour factor from real street routing?

Usage:
    python -m ingest.routing_spike Rome --osrm-url https://routing.openstreetmap.de/routed-foot
    python -m ingest.routing_spike Rome --table osrm_table.json   # a table saved earlier

The sample is drawn from the city's most popular places, because those are the legs an
itinerary actually contains. One OSRM /table request gives route distances and durations for
every ordered pair. Two comparisons come out of it:

- geometry: our estimate against the real street distance walked at OUR speed. This isolates
  the detour factor, which is the only thing the cheap method can get wrong.
- end to end: our estimate against OSRM's own foot durations. The public foot profile
  measured about 4.5 km/h in the Rome run, the same speed we plan with, so there the two
  comparisons agree. The report says so when another server walks at a different speed.

Writes docs/routing-spike.md and docs/routing-spike.json.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date
from pathlib import Path

import numpy as np
import requests

from .cache import write_json, write_text
from .catalog import load_city
from .matrix import DEFAULT_DETOUR, DEFAULT_SPEED_KMH, haversine_km

REPO_ROOT = Path(__file__).resolve().parents[1]

# The scheduler cares about legs a traveler might walk. Past this the leg goes by transit.
MAX_WALK_LEG_MIN = 45.0
# Thresholds for calling the cheap estimate good enough to schedule with.
GOOD_MAE_MIN = 3.0
GOOD_P95_MIN = 8.0


def pick_sample(places: list[dict], n: int = 25, pool: int = 150, seed: int = 7) -> list[dict]:
    """n places drawn at random from the `pool` most popular ones (stable for a given seed)."""
    ranked = sorted(places, key=lambda p: (-p.get("popularity", 0.0), p["id"]))[:pool]
    if len(ranked) < 2:
        raise ValueError("need at least 2 places for a routing sample")
    rng = random.Random(seed)
    return sorted(rng.sample(ranked, min(n, len(ranked))), key=lambda p: p["id"])


def osrm_table(
    sample: list[dict],
    base_url: str,
    profile: str = "foot",
    timeout: int = 60,
    get=requests.get,
) -> dict:
    """One OSRM /table call. Returns {"ids", "durations" (s), "distances" (m)}."""
    coords = ";".join(f"{p['lon']},{p['lat']}" for p in sample)
    resp = get(
        f"{base_url.rstrip('/')}/table/v1/{profile}/{coords}",
        params={"annotations": "duration,distance"},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "Ok" or "durations" not in data or "distances" not in data:
        raise RuntimeError(f"bad OSRM response: code={data.get('code')}")
    return {
        "ids": [p["id"] for p in sample],
        "durations": data["durations"],
        "distances": data["distances"],
    }


def _errors(estimate: np.ndarray, reference: np.ndarray) -> dict:
    diff = estimate - reference
    return {
        "mae_min": round(float(np.mean(np.abs(diff))), 2),
        "p95_abs_min": round(float(np.percentile(np.abs(diff), 95)), 2),
        "bias_min": round(float(np.mean(diff)), 2),
    }


def compare(
    sample: list[dict],
    table: dict,
    speed_kmh: float = DEFAULT_SPEED_KMH,
    detour: float = DEFAULT_DETOUR,
) -> dict:
    """All the numbers for the spike write-up, from one OSRM table."""
    by_id = {p["id"]: p for p in sample}
    places = [by_id[i] for i in table["ids"]]
    lat = np.array([p["lat"] for p in places], dtype=float)
    lon = np.array([p["lon"] for p in places], dtype=float)
    straight = haversine_km(lat, lon, lat, lon)

    rows = []
    for i in range(len(places)):
        for j in range(len(places)):
            dur, dist = table["durations"][i][j], table["distances"][i][j]
            if i == j or dur is None or dist is None or straight[i, j] < 0.05:
                continue
            rows.append((straight[i, j], dist / 1000.0, dur / 60.0))
    if not rows:
        raise ValueError("no usable pairs in the OSRM table")

    km, route_km, osrm_min = (np.array(col) for col in zip(*rows, strict=True))
    ratio = route_km / km
    calibrated = float(np.median(ratio))
    street_min = route_km / speed_kmh * 60.0  # real street distance at our walking speed

    walkable = street_min <= MAX_WALK_LEG_MIN
    methods = {}
    for label, factor in (
        (f"haversine x {detour}", detour),
        (f"haversine x {calibrated:.3f} (sample median)", calibrated),
    ):
        estimate = km * factor / speed_kmh * 60.0
        methods[label] = {
            "detour_factor": round(factor, 3),
            "vs_street_distance": _errors(estimate, street_min),
            "vs_street_distance_walkable_legs": _errors(estimate[walkable], street_min[walkable]),
            "vs_osrm_duration": _errors(estimate, osrm_min),
        }

    return {
        "pairs": len(rows),
        "walkable_pairs": int(walkable.sum()),
        "speed_kmh": speed_kmh,
        "detour_ratio": {
            "median": round(calibrated, 3),
            "mean": round(float(np.mean(ratio)), 3),
            "p10": round(float(np.percentile(ratio, 10)), 3),
            "p90": round(float(np.percentile(ratio, 90)), 3),
        },
        "straight_km": {
            "median": round(float(np.median(km)), 2),
            "max": round(float(np.max(km)), 2),
        },
        "osrm_implied_speed_kmh": round(float(np.median(route_km / (osrm_min / 60.0))), 2),
        "methods": methods,
    }


def _verdict(errors: dict) -> str:
    good = errors["mae_min"] <= GOOD_MAE_MIN and errors["p95_abs_min"] <= GOOD_P95_MIN
    return "Yes" if good else "No"


def _speed_sentence(osrm_speed: float, ours: float) -> str:
    if abs(osrm_speed - ours) <= 0.2:
        return (
            f"The OSRM foot profile walks at about {osrm_speed} km/h, the same as the "
            f"{ours} km/h we plan with, so the gap below is geometry only."
        )
    side = "faster" if osrm_speed > ours else "slower"
    return (
        f"The OSRM foot profile walks at about {osrm_speed} km/h, {side} than the "
        f"{ours} km/h we plan with, so part of this gap is speed, not geometry."
    )


def _decision(result: dict) -> list[str]:
    (default_label, default), (cal_label, calibrated) = result["methods"].items()
    d = default["vs_street_distance_walkable_legs"]
    c = calibrated["vs_street_distance_walkable_legs"]
    if _verdict(d) == "Yes" and d["bias_min"] >= 0:
        choice = (
            f"Keep {default_label}. It passes, and it overestimates a walkable leg by about "
            f"{d['bias_min']:.1f} minutes on average, a small buffer for finding the way. The "
            f"measured median factor ({calibrated['detour_factor']}) is a little tighter but "
            "leaves no slack."
        )
    elif _verdict(c) == "Yes":
        choice = (
            f"Switch the default detour factor to {calibrated['detour_factor']}: the current "
            "default does not pass, the measured one does."
        )
    else:
        return [
            "The cheap estimate is not good enough on its own. Plan a real routing call for "
            "the final itinerary and keep the estimate only for candidate filtering.",
        ]
    return [
        "The cheap estimate is good enough for scheduling. The optimizer keeps the in-process "
        "matrix: no routing call on the request path, so no latency cost in the demo.",
        "",
        choice,
        "",
        "Real routing stays useful for one final check of a finished itinerary.",
    ]


def render(city: str, result: dict, source: str, today: str) -> str:
    rows = []
    for label, m in result["methods"].items():
        e = m["vs_street_distance_walkable_legs"]
        rows.append(
            f"| {label} | {e['mae_min']} | {e['p95_abs_min']} | {e['bias_min']:+} | {_verdict(e)} |"
        )
    end_to_end = []
    for label, m in result["methods"].items():
        e = m["vs_osrm_duration"]
        end_to_end.append(f"| {label} | {e['mae_min']} | {e['p95_abs_min']} | {e['bias_min']:+} |")
    r = result["detour_ratio"]
    return "\n".join(
        [
            "# Routing spike: is haversine x factor good enough to schedule with?",
            "",
            f"Generated {today} by `python -m ingest.routing_spike`. City: {city}. "
            f"Reference: {source}.",
            "",
            f"Sample: {result['pairs']} ordered pairs between popular places, "
            f"{result['walkable_pairs']} of them walkable (at most {MAX_WALK_LEG_MIN:.0f} "
            f"minutes on real streets at {result['speed_kmh']} km/h). Median straight line "
            f"distance {result['straight_km']['median']} km, longest "
            f"{result['straight_km']['max']} km.",
            "",
            "## Answer",
            "",
            "Errors on walkable legs, in minutes, against the real street distance walked at our "
            "planning speed:",
            "",
            "| Method | Mean abs error (min) | p95 error (min) | Bias (min) | Good enough? |",
            "|--------|---------------------:|----------------:|-----------:|--------------|",
            *rows,
            "| OSRM walking | (reference) | (reference) | (reference) | n/a |",
            "",
            f"Good enough means a mean error of at most {GOOD_MAE_MIN:.0f} minutes and a p95 of "
            f"at most {GOOD_P95_MIN:.0f} minutes per leg. A positive bias means we overestimate.",
            "",
            "## Detour ratio (street distance / straight line)",
            "",
            f"Median {r['median']}, mean {r['mean']}, 10th percentile {r['p10']}, "
            f"90th percentile {r['p90']}.",
            "",
            "## All pairs against OSRM durations",
            "",
            _speed_sentence(result["osrm_implied_speed_kmh"], result["speed_kmh"]),
            "Long legs are included here, which is why the errors grow; past the walking "
            "tolerance those legs go by transit anyway.",
            "",
            "| Method | Mean abs error (min) | p95 error (min) | Bias (min) |",
            "|--------|---------------------:|----------------:|-----------:|",
            *end_to_end,
            "",
            "## Decision",
            "",
            *_decision(result),
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compare haversine x factor with OSRM walking.")
    ap.add_argument("city", help="a city the catalog knows, e.g. Rome")
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--osrm-url", help="OSRM base URL with a foot profile")
    source.add_argument("--table", help="saved OSRM table JSON (ids, durations, distances)")
    ap.add_argument("--n", type=int, default=25, help="places in the sample")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--docs", default=str(REPO_ROOT / "docs"))
    args = ap.parse_args(argv)

    city = load_city(args.city)
    if args.table:
        table = json.loads(Path(args.table).read_text(encoding="utf-8"))
        by_id = {p["id"]: p for p in city.places}
        missing = [i for i in table["ids"] if i not in by_id]
        if missing:
            print(f"error: table ids not in {city.name}: {missing[:3]}", file=sys.stderr)
            return 2
        sample = [by_id[i] for i in table["ids"]]
        source_label = table.get("source", args.table)
    else:
        sample = pick_sample(city.places, n=args.n, seed=args.seed)
        table = osrm_table(sample, args.osrm_url)
        source_label = args.osrm_url

    result = compare(sample, table)
    result["city"] = city.name
    result["source"] = source_label

    docs = Path(args.docs)
    docs.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    write_text(docs / "routing-spike.md", render(city.name, result, source_label, today))
    write_json(docs / "routing-spike.json", result, indent=1)
    print(f"wrote {docs / 'routing-spike.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
