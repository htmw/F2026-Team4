"""city name -> geocode -> Overpass -> contract-valid Place[] -> per-city output folder."""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

import requests

from .cache import slugify, utc_now_iso, write_json
from .categories import (
    check_against_vocabulary,
    load_vocabulary,
    unmapped_vocabulary,
)
from .cost import currency_for_country
from .geocode import geocode
from .matrix import (
    DEFAULT_DETOUR,
    DEFAULT_SPEED_KMH,
    matrix_payload,
    select_for_matrix,
    walking_matrix,
)
from .overpass import GROUPS, fetch_group
from .to_place import build_place, make_validator


def run_city(
    query: str,
    *,
    cache_dir: Path,
    out_dir: Path,
    contracts_dir: Path,
    refresh: bool = False,
    groups: list[str] | None = None,
    bbox=None,
    max_span_deg: float = 0.8,
    matrix_top: int = 300,
    speed_kmh: float = DEFAULT_SPEED_KMH,
    detour_factor: float = DEFAULT_DETOUR,
    post=requests.post,
    get=requests.get,
    sleep=time.sleep,
    log=print,
) -> dict:
    contracts_dir = Path(contracts_dir)
    vocab = load_vocabulary(contracts_dir / "categories.json")
    check_against_vocabulary(vocab)
    validator = make_validator(contracts_dir / "place.schema.json")

    geo = geocode(
        query,
        cache_dir,
        refresh=refresh,
        get=get,
        max_span_deg=max_span_deg,
    )
    bbox = tuple(bbox) if bbox else geo.bbox
    currency = currency_for_country(geo.country)
    slug = slugify(query)

    log(f"{geo.display_name}  bbox={bbox}  country={geo.country or '?'}  currency={currency}")

    places: list[dict] = []
    prom: dict[str, int] = {}
    seen: set[tuple] = set()
    counts: Counter = Counter()
    hours_status: Counter = Counter()
    cost_status: Counter = Counter()
    schema_errors: list[str] = []

    for group in groups or list(GROUPS):
        wrapper = fetch_group(
            group,
            bbox,
            cache_dir,
            slug,
            refresh=refresh,
            post=post,
            sleep=sleep,
            log=log,
        )
        fetched = wrapper["fetched_at"][:10]

        for el in wrapper["payload"].get("elements", []):
            key = (el.get("type"), el.get("id"))

            if key in seen:
                continue

            seen.add(key)
            r = build_place(
                el,
                currency=currency,
                fetched_date=fetched,
                validator=validator,
            )

            if r.place is None:
                counts[f"dropped_{r.drop_reason}"] += 1

                if r.error and len(schema_errors) < 5:
                    schema_errors.append(r.error)

                continue

            places.append(r.place)
            prom[r.place["id"]] = r.prominence
            hours_status[r.hours_status] += 1
            cost_status[r.cost_status] += 1
            counts["places"] += 1

    places.sort(key=lambda p: p["id"])

    report = {
        "generated_at": utc_now_iso(),
        "query": query,
        "destination": geo.destination(),
        "bbox": list(bbox),
        "currency_fallback": currency,
        "counts": dict(counts),
        "hours_status": dict(hours_status),
        "cost_status": dict(cost_status),
        "categories": dict(Counter(p["categories"][0] for p in places)),
        "vocabulary_gaps": unmapped_vocabulary(vocab),
        "schema_error_samples": schema_errors,
    }

    out = Path(out_dir) / slug

    write_json(out / "places.json", places, indent=1)
    write_json(out / "destination.json", geo.destination(), indent=1)
    write_json(out / "report.json", report, indent=1)
    write_json(out / "prominence.json", prom)

    if places:
        subset = select_for_matrix(places, prom, matrix_top)
        m = walking_matrix(subset, speed_kmh, detour_factor)

        write_json(
            out / "matrix.json",
            matrix_payload(
                subset,
                m,
                speed_kmh,
                detour_factor,
            ),
        )

    log(f"{len(places)} valid places -> {out}")

    return {
        "destination": geo.destination(),
        "places": places,
        "report": report,
        "out_dir": out,
    }
