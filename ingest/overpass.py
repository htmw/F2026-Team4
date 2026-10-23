"""Fetch POIs from Overpass for a bounding box. Raw responses cached per city+group+bbox."""

from __future__ import annotations

import time
from pathlib import Path

import requests

from .cache import load_cached, store

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
]
REQUEST_TIMEOUT = 180
MAX_ATTEMPTS = 3
BACKOFFS = [5, 15, 45]
HEADERS = {
    "User-Agent": "Wanderwise-Travel-Recommender/1.0 (OpenStreetMap data ingestion)",
}

# Query groups. Nothing here depends on a city: the bbox is the only variable.
# Squares, fountains and neighbourhoods are only fetched when they carry a wikidata tag.
# Without that filter every small piazza and housing estate in a city comes back. Suburbs
# are left out: in OSM they are whole residential districts, not a place to walk around.
GROUPS = {
    "sights": 'nwr["tourism"~"^(attraction|museum|gallery|viewpoint)$"]["name"]({bbox});',
    "historic": 'nwr["historic"]["name"]({bbox});',
    "worship": (
        'nwr["amenity"="place_of_worship"]'
        '["building"~"^(church|cathedral|chapel|basilica)$"]["name"]({bbox});\n'
        '  nwr["amenity"="place_of_worship"]["religion"="christian"]["name"]({bbox});'
    ),
    "nature": (
        'nwr["leisure"~"^(park|garden)$"]["name"]({bbox});\n'
        '  nwr["natural"="beach"]["name"]({bbox});'
    ),
    "food": (
        'nwr["amenity"~"^(restaurant|cafe|marketplace)$"]["name"]({bbox});\n'
        '  nwr["shop"="bakery"]["name"]({bbox});'
    ),
    "nightlife": 'nwr["amenity"~"^(bar|pub|nightclub)$"]["name"]({bbox});',
    "shopping": 'nwr["shop"~"^(mall|department_store|souvenir|gift|antiques)$"]["name"]({bbox});',
    "public_spaces": (
        'nwr["place"="square"]["name"]["wikidata"]({bbox});\n'
        '  nwr["amenity"="fountain"]["name"]["wikidata"]({bbox});'
    ),
    "neighborhoods": 'nwr["place"~"^(neighbourhood|quarter)$"]["name"]["wikidata"]({bbox});',
}


def bbox_string(bbox) -> str:
    """Format a bounding box in Overpass order: south, west, north, east."""
    return ",".join(f"{v:.6f}" for v in bbox)


def build_query(template: str, bbox) -> str:
    """Build an Overpass QL query for the requested bounding box."""
    return (
        f"[out:json][timeout:120];\n(\n  {template.format(bbox=bbox_string(bbox))}\n);\nout center;"
    )


def fetch_overpass(query: str, label: str, *, post=requests.post, sleep=time.sleep, log=print):
    """POST a query, retrying transient failures across available endpoints."""
    last_err: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        for endpoint in ENDPOINTS:
            try:
                log(f"  [{label}] attempt {attempt}/{MAX_ATTEMPTS} -> {endpoint}")
                resp = post(
                    endpoint,
                    data={"data": query},
                    headers=HEADERS,
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                payload = resp.json()

                # Overpass can return HTTP 200 with a remark describing a query failure.
                if (
                    not isinstance(payload, dict)
                    or "elements" not in payload
                    or "remark" in payload
                ):
                    raise RuntimeError(
                        "unexpected Overpass payload: "
                        f"{list(payload) if isinstance(payload, dict) else type(payload).__name__}"
                    )

                log(f"  [{label}] OK ({len(payload['elements'])} elements)")
                return payload, endpoint

            except requests.HTTPError as exc:
                last_err = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                log(f"  [{label}] HTTP failure via {endpoint}: {exc}")

                # Rate limiting and server-side errors may be temporary.
                if status == 429 or (status is not None and status >= 500):
                    continue

                # Permanent client errors, such as HTTP 400, won't improve by retrying
                # the same query against another endpoint.
                raise RuntimeError(f"[{label}] non-retryable HTTP error {status}: {exc}") from exc

            except (requests.ConnectionError, requests.Timeout) as exc:
                last_err = exc
                log(f"  [{label}] connection failure via {endpoint}: {exc}")

            except RuntimeError as exc:
                last_err = exc
                log(f"  [{label}] invalid Overpass response via {endpoint}: {exc}")

        if attempt < MAX_ATTEMPTS:
            delay = BACKOFFS[min(attempt - 1, len(BACKOFFS) - 1)]
            log(f"  [{label}] retrying after {delay}s")
            sleep(delay)

    raise RuntimeError(f"[{label}] exhausted all attempts: {last_err}")


def fetch_group(
    group: str,
    bbox,
    cache_dir: Path,
    slug: str,
    *,
    refresh: bool = False,
    post=requests.post,
    sleep=time.sleep,
    log=print,
) -> dict:
    """Return the cache wrapper {key, fetched_at, endpoint, payload} for one query group."""
    query = build_query(GROUPS[group], bbox)
    key = {"group": group, "bbox": [round(v, 5) for v in bbox], "query": query}
    path = Path(cache_dir) / slug / f"overpass_{group}.json"
    wrapper = None if refresh else load_cached(path, key)

    if wrapper is not None:
        log(f"[{group}] cache hit")
        return wrapper

    payload, endpoint = fetch_overpass(query, group, post=post, sleep=sleep, log=log)
    wrapper = store(path, key, payload, endpoint=endpoint)
    sleep(2)  # Be polite to the public API.
    return wrapper


def fetch_combined(
    groups,
    bbox,
    cache_dir: Path,
    slug: str,
    *,
    refresh: bool = False,
    post=requests.post,
    sleep=time.sleep,
    log=print,
) -> dict:
    """Like fetch_group, but every group in one request. The live fetch uses it so the
    traveler waits for one query, not nine with a pause between each."""
    groups = list(groups)
    query = build_query("\n  ".join(GROUPS[g] for g in groups), bbox)
    key = {"groups": groups, "bbox": [round(v, 5) for v in bbox], "query": query}
    path = Path(cache_dir) / slug / "overpass_combined.json"
    wrapper = None if refresh else load_cached(path, key)

    if wrapper is not None:
        log("[combined] cache hit")
        return wrapper

    payload, endpoint = fetch_overpass(query, "combined", post=post, sleep=sleep, log=log)
    return store(path, key, payload, endpoint=endpoint)
