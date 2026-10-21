"""Step 3 of the pipeline: turn one OSM element into a Place record, or say why not.

build_place() takes one element from an Overpass response (its type, id, position and
tags) and returns a BuildResult: the Place, valid against contracts/place.schema.json, or
the reason it was dropped. It also keeps a few tag facts (signals) that the popularity,
dedupe and curation steps need later.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .categories import DEFAULT_DURATION_MIN, DEFAULT_HOURS, map_categories
from .cost import parse_cost
from .hours import DAYS, parse_opening_hours
from .popularity import signals_from_tags

# Name tags kept for matching curated entries and duplicates. old_name is left out on
# purpose: it often belongs to a different, earlier place at the same spot.
_NAME_TAG = re.compile(r"^(name|alt_name|official_name|int_name|short_name)(:[A-Za-z-]+)?$")

# City walls and aqueducts are mapped as many short pieces that share one name: Lisbon has
# 36 pieces of the Aguas Livres aqueduct. Dedupe turns each structure back into one stop.
_LONG_STRUCTURE_TAGS = {
    ("historic", "citywalls"),
    ("historic", "aqueduct"),
    ("barrier", "city_wall"),
    ("man_made", "city_wall"),
    ("man_made", "aqueduct"),
}

# Relations that group separate parts. Overpass places them at the centre of the bounding
# box of all the parts, which can be far from every part: a ring of city walls has its
# centre in the middle of the city, far from any wall.
_COLLECTION_RELATIONS = {"site", "route", "building", "waterway", "collection", "multilinestring"}


def is_long_structure(tags: dict) -> bool:
    return any(tags.get(key) == value for key, value in _LONG_STRUCTURE_TAGS)


@dataclass
class BuildResult:
    """What build_place() returns: a Place, or the reason it was dropped."""

    place: dict | None
    # no_name, no_coords, unmapped_category, always_closed or schema_invalid
    drop_reason: str | None = None
    error: str | None = None  # the schema error message when drop_reason is schema_invalid
    cost_status: str | None = None  # how the price was found, see cost.parse_cost()
    # Facts from the OSM tags that later steps need (popularity, dedupe, curation). They are
    # not part of the Place contract and are not written to places.json.
    signals: dict = field(default_factory=dict)


def make_validator(schema_path: Path) -> Draft202012Validator:
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def normalize_name(text: str) -> str:
    """Lowercase, strip accents and punctuation, so spellings of one name compare equal.

    Example: Padrão dos Descobrimentos -> padrao dos descobrimentos
    """
    decomposed = unicodedata.normalize("NFKD", text)
    no_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^\w]+", " ", no_marks.casefold()).split())


def name_variants(tags: dict) -> list[str]:
    """Every normalised name the place is known by, in any language."""
    names = {normalize_name(v) for k, v in tags.items() if _NAME_TAG.match(k) and v}
    names.discard("")
    return sorted(names)


def element_id(el: dict) -> str:
    return f"osm:{el['type']}/{el['id']}"


def _coords(el: dict):
    if el.get("type") == "node":
        return el.get("lat"), el.get("lon")
    center = el.get("center") or {}
    return center.get("lat"), center.get("lon")


def default_hours(primary: str) -> dict:
    """The category default hours, every day of the week, labelled inferred."""
    windows = [list(w) for w in DEFAULT_HOURS[primary]]
    hours = {d: [list(w) for w in windows] for d in DAYS}
    hours["confidence"] = "inferred"
    return hours


def unknown_hours() -> dict:
    """Hours we could not read. Every day is null, which here means no information, not
    closed: anyone reading hours must check the confidence first."""
    hours = {d: None for d in DAYS}
    hours["confidence"] = "unknown"
    return hours


def build_place(
    el: dict, *, currency: str, fetched_date: str, validator: Draft202012Validator
) -> BuildResult:
    """One OSM element -> BuildResult. currency is used when a price has none of its own,
    fetched_date becomes last_verified."""
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
        # "off" for every day of the week: closed for good or for a long restoration.
        # A planner can never schedule it, so it only wastes a candidate slot.
        if all(hours[d] is None for d in DAYS):
            return BuildResult(None, "always_closed")
    elif parsed.status == "absent":
        hours = default_hours(cats[0])
    else:
        hours = unknown_hours()

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

    signals = signals_from_tags(tags)
    signals["osm_type"] = el.get("type")
    signals["names"] = name_variants(tags)
    signals["long_structure"] = is_long_structure(tags)
    signals["rough_point"] = el.get("type") == "relation" and tags.get("type") in (
        _COLLECTION_RELATIONS
    )
    return BuildResult(place, cost_status=cost.status, signals=signals)
