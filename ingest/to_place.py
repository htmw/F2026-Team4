"""Convert OSM elements into valid Place records, dropping invalid ones."""

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
from .popularity import documentation_count, signals_from_tags

# Name tags kept for matching curated entries and duplicates. old_name is left out on
# purpose: it often belongs to a different, earlier place at the same spot.
_NAME_TAG = re.compile(r"^(name|alt_name|official_name|int_name|short_name)(:[A-Za-z-]+)?$")

# City walls and aqueducts are mapped as many short pieces that share one name: Rome has
# about 90 pieces of the Aurelian Walls. Dedupe turns each structure back into one stop.
_LONG_STRUCTURE_TAGS = {
    ("historic", "citywalls"),
    ("historic", "aqueduct"),
    ("barrier", "city_wall"),
    ("man_made", "city_wall"),
    ("man_made", "aqueduct"),
}

# Relations that group separate parts. Overpass places them at the centre of the bounding
# box of all the parts, which can be far from every part: the ring of the Aurelian Walls
# has its centre next to the Colosseum.
_COLLECTION_RELATIONS = {"site", "route", "building", "waterway", "collection", "multilinestring"}


def is_long_structure(tags: dict) -> bool:
    return any(tags.get(key) == value for key, value in _LONG_STRUCTURE_TAGS)


@dataclass
class BuildResult:
    place: dict | None
    # no_name | no_coords | unmapped_category | always_closed | schema_invalid
    drop_reason: str | None = None
    hours_status: str | None = None  # parsed | absent | unparseable
    cost_status: str | None = None
    prominence: int = 0
    error: str | None = None
    # Tag facts the later steps need (popularity, dedupe, curation). Not part of the contract.
    signals: dict = field(default_factory=dict)


def make_validator(schema_path: Path) -> Draft202012Validator:
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def prominence(tags: dict) -> int:
    """How many documentation tags a place has (website, hours, wikidata...)."""
    return documentation_count(tags)


def normalize_name(text: str) -> str:
    """Lowercase, strip accents and punctuation, so Castel Sant'Angelo matches sant angelo."""
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


_SCHOOLS = {"school", "college", "university", "kindergarten"}
# Kinds of place OSM tags by the thousand, most of them unknown outside their street: every
# vegetable and footwear market, every memorial plaque, every named viewpoint. Only the
# famous ones are sights. Typed sights (museum, palace, park...), venues, and the pieces of
# a city wall or aqueduct (dedupe joins them into one stop) stay.
_ONLY_FAMOUS = {"market", "landmark", "viewpoint"}


def _famous(tags: dict) -> bool:
    return any(tags.get(key) for key in ("wikidata", "wikipedia", "heritage"))


def _unknown_school(tags: dict) -> bool:
    """A school, college or university nobody outside it would visit.

    Mappers sometimes tag one as an attraction or a viewpoint: a college in Karimnagar is
    tagged tourism=viewpoint. Famous ones (Coimbra, the Oxford colleges) carry Wikidata,
    Wikipedia or heritage tags and stay.
    """
    school = (
        tags.get("amenity") in _SCHOOLS
        or tags.get("building") in _SCHOOLS
        or any(key in tags for key in _SCHOOLS)
    )
    return school and not _famous(tags)


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
    if _unknown_school(tags):
        return BuildResult(None, "school")
    if cats[0] in _ONLY_FAMOUS and not _famous(tags) and not is_long_structure(tags):
        return BuildResult(None, "not_famous")

    parsed = parse_opening_hours(tags.get("opening_hours"))
    if parsed.status == "parsed":
        hours = parsed.hours
        # "off" for every day of the week: closed for good or for a long restoration.
        # A planner can never schedule it, so it only wastes a candidate slot.
        if all(hours[d] is None for d in DAYS):
            return BuildResult(None, "always_closed", hours_status=parsed.status)
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

    signals = signals_from_tags(tags)
    signals["osm_type"] = el.get("type")
    signals["names"] = name_variants(tags)
    signals["long_structure"] = is_long_structure(tags)
    signals["rough_point"] = el.get("type") == "relation" and tags.get("type") in (
        _COLLECTION_RELATIONS
    )
    return BuildResult(
        place, None, parsed.status, cost.status, prominence(tags), signals=signals
    )
