"""Build the place data for one city: city name in, a folder of JSON files out.

run_city() does these steps in order. The comments in the code use the same numbers.

1. Geocode the name with Nominatim: centre, country and the area to search (the bbox).
2. Download each Overpass query group for that area (cached on disk, see overpass.py).
3. Turn every OSM element into a Place record (to_place.py). Elements with no name, no
   position or no category we map are dropped, and so is anything outside the bbox.
4. Give each place a popularity score from its OSM tags (popularity.py).
5. Merge duplicate records of the same real place (dedupe.py).
6. Apply the hand checked curation file, if there is one (curation.py).
7. Write places.json, destination.json, city.json and report.json to out_dir/<slug>/.

make snapshot-lisbon runs it for Lisbon and writes the result to data/cities/lisbon/.
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

import requests

from .cache import slugify, utc_now_iso, write_json, write_json_lines_array
from .categories import check_against_vocabulary, load_vocabulary, unmapped_vocabulary
from .cost import currency_for_country
from .curation import apply_curation, load_curation
from .dedupe import dedupe
from .geocode import DEFAULT_MAX_SPAN_KM, geocode
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
    slug: str | None = None,
    aliases: list[str] | None = None,
    curation_path: Path | None = None,
    post=requests.post,
    get=requests.get,
    sleep=time.sleep,
    log=print,
) -> dict:
    """Run every step for one city and return {destination, places, report, out_dir}.

    query: the city name, e.g. Lisbon, Portugal.
    bbox: an explicit search area (south, west, north, east). Without it the geocoded
        city boundary is used.
    slug: the output folder name, e.g. lisbon. Defaults to one made from the query.
    aliases: extra names the API should accept for this city, e.g. Lisboa.
    refresh: download again even when the cache has the data.
    post, get, sleep and log let tests run the whole pipeline without the network.
    """
    contracts_dir = Path(contracts_dir)
    vocab = load_vocabulary(contracts_dir / "categories.json")
    check_against_vocabulary(vocab)
    validator = make_validator(contracts_dir / "place.schema.json")
    # Read the curation file first, so a typo in it stops the run before any download.
    curation = load_curation(curation_path) if curation_path else None

    # 1. Geocode. With an explicit bbox the geocoded box is only used for the name,
    # country and centre, so its size does not matter and the size check is skipped.
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
    signals: dict[str, dict] = {}  # place id -> tag facts that dedupe and curation need
    seen: set[tuple] = set()
    counts: Counter = Counter()
    schema_errors: list[str] = []

    for group in groups or list(GROUPS):
        # 2. Download one query group (or read it from the cache).
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
            # The same element can come back in two groups (a museum that is also historic).
            key = (el.get("type"), el.get("id"))
            if key in seen:
                continue
            seen.add(key)

            # 3. Convert, or drop with a reason that ends up in report.json.
            r = build_place(el, currency=currency, fetched_date=fetched, validator=validator)
            if r.place is None:
                counts[f"dropped_{r.drop_reason}"] += 1
                if r.error and len(schema_errors) < 5:
                    schema_errors.append(r.error)
                continue

            # Overpass also returns ways and relations that only touch the box, and their
            # centre can lie outside it. The Lisbon run drops 8 such places, for example a
            # park in Loures 9 km from the city centre. The planner only works inside the box.
            if not _inside(r.place, bbox):
                counts["dropped_outside_bbox"] += 1
                continue

            # 4. Popularity.
            r.place["popularity"] = popularity(r.signals)
            r.signals["cost_status"] = r.cost_status
            places.append(r.place)
            signals[r.place["id"]] = r.signals
            counts["valid_records"] += 1

    # 5. Merge duplicates.
    places, dedupe_report = dedupe(places, signals)
    if dedupe_report.no_position:
        counts["dropped_no_position"] = len(dedupe_report.no_position)

    # 6. Curation.
    curation_report = None
    if curation is not None:
        places, applied = apply_curation(places, curation, signals, validator)
        curation_report = applied.as_dict()
        for name in applied.unmatched:
            log(f"  curation: no match for {name!r}")

    # 7. Write the output folder.
    places.sort(key=lambda p: p["id"])
    counts["places"] = len(places)
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
        "hours_status": dict(Counter(_hours_label(p) for p in places)),
        "cost_status": dict(Counter(_cost_label(p, signals.get(p["id"], {})) for p in places)),
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

    out = Path(out_dir) / out_slug
    write_json_lines_array(out / "places.json", places)
    write_json(out / "destination.json", destination, indent=1)
    write_json(out / "city.json", city, indent=1)
    write_json(out / "report.json", report, indent=1)
    log(f"{len(places)} places ({dedupe_report.merged} duplicates merged) -> {out}")

    return {"destination": destination, "places": places, "report": report, "out_dir": out}


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
