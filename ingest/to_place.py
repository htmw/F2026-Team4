"""Convert OSM elements into valid Place records, dropping invalid ones."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .categories import DEFAULT_DURATION_MIN, DEFAULT_HOURS, map_categories
from .cost import parse_cost
from .hours import DAYS, parse_opening_hours

_PROMINENCE_KEYS = (
    "wikidata",
    "wikipedia",
    "heritage",
    "website",
    "contact:website",
    "opening_hours",
    "fee",
    "charge",
    "description",
)


@dataclass
class BuildResult:
    place: dict | None
    drop_reason: str | None = None  # no_name | no_coords | unmapped_category | schema_invalid
    hours_status: str | None = None  # parsed | absent | unparseable
    cost_status: str | None = None
    prominence: int = 0
    error: str | None = None


def make_validator(schema_path: Path) -> Draft202012Validator:
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def prominence(tags: dict) -> int:
    """Crude, city-agnostic 'how documented is this place' score. Used only to cap matrix size."""
    return sum(1 for k in _PROMINENCE_KEYS if tags.get(k))


def element_id(el: dict) -> str:
    return f"osm:{el['type']}/{el['id']}"


def _coords(el: dict):
    if el.get("type") == "node":
        return el.get("lat"), el.get("lon")
    center = el.get("center") or {}
    return center.get("lat"), center.get("lon")


def _default_hours(primary: str) -> dict:
    windows = [list(w) for w in DEFAULT_HOURS[primary]]
    hours = {d: [list(w) for w in windows] for d in DAYS}
    hours["confidence"] = "inferred"
    return hours


def _unknown_hours() -> dict:
    hours = {
        d: None for d in DAYS
    }  # NOTE: null means closed; consumers must check confidence first
    hours["confidence"] = "unknown"
    return hours


def build_place(
    el: dict, *, currency: str, fetched_date: str, validator: Draft202012Validator
) -> BuildResult:
    tags = el.get("tags") or {}
    name = (tags.get("name") or "").strip()
    if not name:
        return BuildResult(None, "no_name")
    lat, lon = _coords(el)
    if lat is None or lon is None:
        return BuildResult(None, "no_coords")
    cats = map_categories(tags)
    if not cats:
        return BuildResult(None, "unmapped_category")

    parsed = parse_opening_hours(tags.get("opening_hours"))
    if parsed.status == "parsed":
        hours = parsed.hours
    elif parsed.status == "absent":
        hours = _default_hours(cats[0])
    else:
        hours = _unknown_hours()

    cost = parse_cost(tags, cats, currency)
    place = {
        "id": element_id(el),
        "name": name,
        "lat": float(lat),
        "lon": float(lon),
        "categories": cats,
        "typical_duration_minutes": max(DEFAULT_DURATION_MIN[c] for c in cats),
        "cost": cost.cost,
        "hours": hours,
        "source": "osm",
        "last_verified": fetched_date,
    }
    errors = sorted(validator.iter_errors(place), key=lambda e: list(e.path))
    if errors:
        return BuildResult(None, "schema_invalid", error=errors[0].message)
    return BuildResult(place, None, parsed.status, cost.status, prominence(tags))
