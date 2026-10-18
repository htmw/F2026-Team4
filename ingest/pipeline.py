"""city name -> geocode -> Overpass -> contract-valid Place[] -> per-city output folder.

Steps, in order:
1. geocode the name (Nominatim) for the centre, country and default bounding box,
2. fetch every Overpass query group for the box (raw responses cached on disk),
3. convert each OSM element to a Place, dropping the ones that cannot be valid or whose
   centre falls outside the box,
4. score popularity from the OSM tags,
5. merge duplicate records of the same place, and the pieces of each wall or aqueduct,
6. apply the hand checked curation file, if there is one,
7. write places.json, destination.json, city.json, report.json and matrix.json.
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

import requests

from .cache import slugify, utc_now_iso, write_json, write_json_lines_array
from .categories import (
    check_against_vocabulary,
    load_vocabulary,
    unmapped_vocabulary,
)
from .cost import currency_for_country
from .curation import apply_curation, load_curation
from .dedupe import dedupe
from .geocode import DEFAULT_MAX_SPAN_KM, geocode
from .matrix import (
    DEFAULT_DETOUR,
    DEFAULT_SPEED_KMH,
    TravelModel,
    matrix_payload,
    select_for_matrix,
    transit_matrix,
    walking_matrix,
)
from .overpass import GROUPS, fetch_group
from .popularity import popularity
from .to_place import build_place, make_validator

OSM_ATTRIBUTION = "Data (c) OpenStreetMap contributors, ODbL 1.0, https://www.openstreetmap.org/copyright"


def run_city(
    query: str,
    *,
    cache_dir: Path,
    out_dir: Path,
    contracts_dir: Path,
    refresh: bool = False,
    groups: list[str] | None = None,
    bbox=None,
    max_span_km: float = DEFAULT_MAX_SPAN_KM,
    matrix_top: int = 300,
    speed_kmh: float = DEFAULT_SPEED_KMH,
    detour_factor: float = DEFAULT_DETOUR,
    slug: str | None = None,
    aliases: list[str] | None = None,
    curation_path: Path | None = None,
    post=requests.post,
    get=requests.get,
    sleep=time.sleep,
    log=print,
) -> dict:
    contracts_dir = Path(contracts_dir)
    vocab = load_vocabulary(contracts_dir / "categories.json")
    check_against_vocabulary(vocab)
    validator = make_validator(contracts_dir / "place.schema.json")
    curation = load_curation(curation_path) if curation_path else None

    # With an explicit bbox the geocoded box is only used for the name, country and centre,
    # so its size does not matter (London, Tokyo, or any city whose admin area is huge).
    geo = geocode(
        query,
        cache_dir,
        refresh=refresh,
        get=get,
        max_span_km=None if bbox else max_span_km,
    )
    bbox_source = "explicit" if bbox else "geocoded"
    bbox = tuple(bbox) if bbox else geo.bbox
    currency = currency_for_country(geo.country)
    cache_slug = slugify(query)
    out_slug = slug or cache_slug

    log(f"{geo.display_name}  bbox={bbox}  country={geo.country or '?'}  currency={currency}")

    places: list[dict] = []
    signals: dict[str, dict] = {}
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
            cache_slug,
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

            # Overpass returns ways and relations that only touch the box. Their centre can
            # be far outside it (a Roman aqueduct relation lands 17 km east of the centre),
            # and the planner only works inside the box.
            if not _inside(r.place, bbox):
                counts["dropped_outside_bbox"] += 1
                continue

            r.place["popularity"] = popularity(r.signals)
            r.signals["cost_status"] = r.cost_status
            places.append(r.place)
            signals[r.place["id"]] = r.signals
            counts["valid_records"] += 1

    places, dedupe_report = dedupe(places, signals)
    if dedupe_report.no_position:
        counts["dropped_no_position"] = len(dedupe_report.no_position)

    curation_report = None
    if curation is not None:
        places, report = apply_curation(places, curation, signals, validator)
        curation_report = report.as_dict()
        for name in report.unmatched:
            log(f"  curation: no match for {name!r}")

    places.sort(key=lambda p: p["id"])
    counts["places"] = len(places)
    for p in places:
        hours_status[_hours_label(p)] += 1
        cost_status[_cost_label(p, signals.get(p["id"], {}))] += 1

    destination = geo.destination()
    report = {
        "generated_at": utc_now_iso(),
        "query": query,
        "destination": destination,
        "bbox": list(bbox),
        "bbox_source": bbox_source,
        "currency_fallback": currency,
        "counts": dict(counts),
        "duplicates": dedupe_report.as_dict(),
        "hours_status": dict(hours_status),
        "cost_status": dict(cost_status),
        "categories": dict(Counter(p["categories"][0] for p in places)),
        "vocabulary_gaps": unmapped_vocabulary(vocab),
        "curation": curation_report,
        "schema_error_samples": schema_errors,
    }
    city = {
        "key": out_slug,
        "name": destination["name"],
        "country": destination.get("country", ""),
        "country_name": geo.country_name,
        "aliases": sorted({a for a in [query, destination["name"], *(aliases or [])] if a}),
        "lat": destination.get("lat"),
        "lon": destination.get("lon"),
        "bbox": list(bbox),
        "bbox_source": bbox_source,
        "currency": currency,
        "places": len(places),
        "built_at": report["generated_at"],
        "curation": Path(curation_path).name if curation_path else None,
        "attribution": OSM_ATTRIBUTION,
    }

    # Build the matrix before writing anything, so a failure here (bad speed, too many
    # places) never leaves a new places.json next to an old matrix.json.
    # matrix_top=0 means no matrix file at all (the API builds legs on demand).
    matrix = None
    if matrix_top > 0:
        model = TravelModel(walk_speed_kmh=speed_kmh, walk_detour=detour_factor)
        subset = select_for_matrix(places, matrix_top)
        matrix = matrix_payload(
            subset,
            walking_matrix(subset, speed_kmh, detour_factor),
            speed_kmh,
            detour_factor,
            transit=transit_matrix(subset, model),
            model=model,
        )

    out = Path(out_dir) / out_slug
    write_json_lines_array(out / "places.json", places)
    write_json(out / "destination.json", destination, indent=1)
    write_json(out / "city.json", city, indent=1)
    write_json(out / "report.json", report, indent=1)

    # The matrix always describes the places.json written next to it, even after an empty run.
    matrix_file = out / "matrix.json"
    if matrix is not None:
        write_json(matrix_file, matrix)
    elif matrix_file.exists():
        matrix_file.unlink()

    log(f"{len(places)} places ({dedupe_report.merged} duplicates merged) -> {out}")

    return {
        "destination": destination,
        "places": places,
        "report": report,
        "out_dir": out,
    }


def _inside(place: dict, bbox) -> bool:
    south, west, north, east = bbox
    return south <= place["lat"] <= north and west <= place["lon"] <= east


def _hours_label(place: dict) -> str:
    """parsed (real or curated hours), absent (category default used) or unparseable."""
    labels = {"known": "parsed", "inferred": "absent"}
    return labels.get(place["hours"]["confidence"], "unparseable")


def _cost_label(place: dict, signals: dict) -> str:
    """Same labels as cost.parse_cost, read from the final record after dedupe and curation."""
    cost = place["cost"]
    if cost["confidence"] == "known":
        return "charge_parsed" if cost["amount"] > 0 else "fee_free"
    if cost["confidence"] == "inferred":
        return "default_free"
    status = signals.get("cost_status")
    return status if status in {"fee_amount_missing", "charge_ambiguous"} else "no_data"
