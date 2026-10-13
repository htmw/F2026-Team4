#!/usr/bin/env python3
"""Pull Rome places from the Overpass API and load them into SQLite.

Queries Overpass for places in Rome's historic center, saves each raw JSON
response in data/raw/ (it is only downloaded again with --refresh) and puts
cleaned rows in the places table. Places without a name are dropped and
counted in ingest_runs.

Usage:
    python3 extract_rome.py                 # uses the cache if it exists
    python3 extract_rome.py --refresh       # download everything again
    python3 extract_rome.py --only food     # one query only (sights|historic|food|parks)

Needs: requests
"""

import argparse
import json
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
DEFAULT_DB = DATA_DIR / "wanderwise_rome.db"
SCHEMA_FILE = BASE_DIR / "schema.sql"

DEFAULT_BBOX = "41.87,12.43,41.94,12.53"  # s,w,n,e — Rome historic center

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
]

# One query per group. Overpass wants the bbox as south, west, north, east.
QUERIES = {
    "sights": ('nwr["tourism"~"^(attraction|museum|gallery|viewpoint)$"]["name"]({bbox});'),
    "historic": 'nwr["historic"]["name"]({bbox});',
    "food": 'nwr["amenity"~"^(restaurant|cafe)$"]["name"]({bbox});',
    "parks": 'nwr["leisure"~"^(park|garden)$"]["name"]({bbox});',
}

REQUEST_TIMEOUT = 180  # seconds per request (the query itself has a 120 s limit)
MAX_ATTEMPTS = 3
BACKOFFS = [5, 15, 45]  # seconds to wait between rounds


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def build_query(template: str, bbox: str) -> str:
    return f"[out:json][timeout:120];\n(\n  {template.format(bbox=bbox)}\n);\nout center;"


def fetch_overpass(query: str, label: str) -> tuple[dict, str]:
    """Send the query to Overpass, trying the next endpoint if one fails.

    Returns (json, endpoint_used). Raises RuntimeError if everything fails.
    """
    last_err: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        for endpoint in ENDPOINTS:
            try:
                print(f"  [{label}] attempt {attempt}/{MAX_ATTEMPTS} -> {endpoint}", flush=True)
                resp = requests.post(endpoint, data={"data": query}, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                payload = resp.json()
                if "elements" not in payload:
                    raise RuntimeError(f"unexpected Overpass payload keys: {list(payload.keys())}")
                print(
                    f"  [{label}] OK via {endpoint} ({len(payload['elements'])} elements)",
                    flush=True,
                )
                return payload, endpoint
            except Exception as exc:  # any failure -> try the next endpoint
                last_err = exc
                print(f"  [{label}] failed via {endpoint}: {exc}", flush=True)
        if attempt < MAX_ATTEMPTS:
            wait = BACKOFFS[attempt - 1]
            print(f"  [{label}] all endpoints failed, backing off {wait}s...", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"[{label}] exhausted all attempts: {last_err}")


def extract_address(tags: dict) -> str | None:
    parts = [
        tags.get("addr:housenumber", ""),
        tags.get("addr:street", ""),
        tags.get("addr:postcode", ""),
        tags.get("addr:city", ""),
    ]
    addr = " ".join(p for p in (parts[0], parts[1]) if p).strip()
    city = " ".join(p for p in (parts[2], parts[3]) if p).strip()
    full = ", ".join(p for p in (addr, city) if p).strip()
    return full or None


def extract_fee(tags: dict) -> str:
    fee = (tags.get("fee") or "").strip().lower()
    if fee in ("yes", "no"):
        return fee
    if tags.get("charge"):
        return "yes"
    return "unknown"


def categorize(element: dict, query_label: str) -> tuple[str, str | None]:
    """Work out (category, subcategory) for an OSM element."""
    tags = element.get("tags", {})
    if query_label == "food":
        return "food", tags.get("amenity")
    if query_label == "parks":
        return "park", tags.get("leisure")
    if query_label == "historic":
        return "attraction", tags.get("historic")
    tourism = tags.get("tourism", "")
    if tourism == "museum":
        return "museum", "museum"
    if tourism == "gallery":
        return "museum", "gallery"
    if tourism == "viewpoint":
        return "viewpoint", "viewpoint"
    return "attraction", tourism or None


def normalize(element: dict, query_label: str, ingested_at: str) -> dict | None:
    """Turn one Overpass element into a places row, or None if it has no name or coordinates."""
    tags = element.get("tags") or {}
    name = (tags.get("name") or "").strip()
    if not name:
        return None
    if element["type"] == "node":
        lat, lon = element.get("lat"), element.get("lon")
    else:
        center = element.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")
    if lat is None or lon is None:
        return None
    category, subcategory = categorize(element, query_label)
    return {
        "osm_type": element["type"],
        "osm_id": element["id"],
        "name": name,
        "category": category,
        "subcategory": subcategory,
        "lat": lat,
        "lon": lon,
        "opening_hours": tags.get("opening_hours"),
        "fee": extract_fee(tags),
        "website": tags.get("website") or tags.get("contact:website"),
        "phone": tags.get("phone") or tags.get("contact:phone"),
        "address": extract_address(tags),
        "tags_json": json.dumps(tags, ensure_ascii=False, sort_keys=True),
        "source": "overpass",
        "curated": 0,
        "ingested_at": ingested_at,
    }


UPSERT_SQL = """
INSERT INTO places (osm_type, osm_id, name, category, subcategory, lat, lon,
                    opening_hours, fee, website, phone, address, tags_json,
                    source, curated, ingested_at)
VALUES (:osm_type, :osm_id, :name, :category, :subcategory, :lat, :lon,
        :opening_hours, :fee, :website, :phone, :address, :tags_json,
        :source, :curated, :ingested_at)
ON CONFLICT (osm_type, osm_id) DO UPDATE SET
    name=excluded.name, category=excluded.category,
    subcategory=excluded.subcategory, lat=excluded.lat, lon=excluded.lon,
    opening_hours=excluded.opening_hours, fee=excluded.fee,
    website=excluded.website, phone=excluded.phone, address=excluded.address,
    tags_json=excluded.tags_json, ingested_at=excluded.ingested_at
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract Rome places from Overpass.")
    ap.add_argument(
        "--refresh", action="store_true", help="re-download raw responses even if cached"
    )
    ap.add_argument("--db", default=str(DEFAULT_DB), help="SQLite db path")
    ap.add_argument("--bbox", default=DEFAULT_BBOX, help="s,w,n,e bounding box")
    ap.add_argument("--only", choices=list(QUERIES), help="run only one query group (for testing)")
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_FILE.read_text())
    started_at = utcnow()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ingest_runs (started_at, bbox, notes) VALUES (?, ?, ?)",
        (started_at, args.bbox, " ".join(sys.argv)),
    )
    run_id = cur.lastrowid
    conn.commit()

    labels = [args.only] if args.only else list(QUERIES)
    print(f"bbox={args.bbox}  db={db_path}  queries={labels}", flush=True)

    per_category: dict[str, int] = {}
    dropped_nameless = 0
    endpoints_used: set[str] = set()
    seen: set[tuple[str, int]] = set()  # same place can show up in two query groups
    ingested_at = utcnow()

    try:
        for label in labels:
            cache_file = RAW_DIR / f"{label}.json"
            if cache_file.exists() and not args.refresh:
                print(f"[{label}] using cached {cache_file}", flush=True)
                payload = json.loads(cache_file.read_text())
                endpoint = "cache"
            else:
                query = build_query(QUERIES[label], args.bbox)
                payload, endpoint = fetch_overpass(query, label)
                cache_file.write_text(json.dumps(payload, ensure_ascii=False))
                print(f"[{label}] cached -> {cache_file}", flush=True)
                time.sleep(2)  # don't hammer the public API
            endpoints_used.add(endpoint)

            inserted = 0
            for el in payload.get("elements", []):
                key = (el.get("type"), el.get("id"))
                if key in seen:
                    continue
                row = normalize(el, label, ingested_at)
                if row is None:
                    dropped_nameless += 1
                    continue
                seen.add(key)
                cur.execute(UPSERT_SQL, row)
                inserted += 1
                per_category[row["category"]] = per_category.get(row["category"], 0) + 1
            conn.commit()
            print(
                f"[{label}] normalized {inserted} named places "
                f"(dropped nameless so far: {dropped_nameless})",
                flush=True,
            )

        cur.execute(
            """UPDATE ingest_runs SET finished_at=?, endpoint=?, counts_json=?,
                   dropped_nameless=?, notes=? WHERE run_id=?""",
            (
                utcnow(),
                ",".join(sorted(endpoints_used)),
                json.dumps(per_category, sort_keys=True),
                dropped_nameless,
                f"refresh={args.refresh}",
                run_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    total = sum(per_category.values())
    print(
        f"DONE: {total} places "
        f"({', '.join(f'{k}={v}' for k, v in sorted(per_category.items()))}), "
        f"dropped nameless={dropped_nameless}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
