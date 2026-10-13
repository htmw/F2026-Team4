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

# Query groups. Nothing here depends on a city: the bbox is the only variable.
GROUPS = {
    "sights": 'nwr["tourism"~"^(attraction|museum|gallery|viewpoint)$"]["name"]({bbox});',
    "historic": 'nwr["historic"]["name"]({bbox});',
    "worship": (
        'nwr["amenity"="place_of_worship"]'
        '["building"~"^(church|cathedral|chapel|basilica)$"]["name"]({bbox});'
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
}


def bbox_string(bbox) -> str:
    return ",".join(f"{v:.6f}" for v in bbox)  # Overpass order: south,west,north,east


def build_query(template: str, bbox) -> str:
    return (
        f"[out:json][timeout:120];\n(\n  {template.format(bbox=bbox_string(bbox))}\n);\nout center;"
    )


def fetch_overpass(query: str, label: str, *, post=requests.post, sleep=time.sleep, log=print):
    """POST the query, trying each endpoint in turn, with backoff between rounds."""
    last_err: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        for endpoint in ENDPOINTS:
            try:
                log(f"  [{label}] attempt {attempt}/{MAX_ATTEMPTS} -> {endpoint}")
                resp = post(endpoint, data={"data": query}, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                payload = resp.json()
                if "elements" not in payload:
                    raise RuntimeError(f"unexpected Overpass payload keys: {list(payload)}")
                log(f"  [{label}] OK ({len(payload['elements'])} elements)")
                return payload, endpoint
            except Exception as exc:
                last_err = exc
                log(f"  [{label}] failed via {endpoint}: {exc}")
        if attempt < MAX_ATTEMPTS:
            sleep(BACKOFFS[attempt - 1])
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
    sleep(2)  # be polite to the public API
    return wrapper
