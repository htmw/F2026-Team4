"""Hand checked corrections for the places that matter most in a city.

OSM coverage of opening hours and prices is patchy, and the gaps are worst exactly where a
traveler needs certainty: the big ticketed sights. For those, a person checks the official
website and writes the facts into data/curation/<city>.json. This module applies that file
on top of the OSM records.

Rules:
- Curated hours use the same OpenStreetMap syntax and the same strict parser as OSM data.
  If the parser cannot read them, the run stops: a typo must never become a known fact.
- A curated field is labelled `known` when it comes from the official source. An entry with
  "confidence": "low" (secondary sources only, or sources that disagree) is applied as
  `inferred`, so the optimizer treats it as a soft constraint, not a fact.
- The record's source becomes `osm+curated` and `last_verified` becomes the date the person
  checked the source.
- An entry that matches no place is reported, not silently dropped.

File shape (JSON):

    {
      "city": "rome",
      "checked_on": "2026-10-17",
      "valid_for": "winter timetable 2026/27",
      "places": [
        {
          "name": "Colosseum",
          "match": {"names": ["Colosseo"], "near": [41.8902, 12.4922], "radius_m": 300},
          "opening_hours": "Mo-Su 08:30-16:30",
          "price": {"amount": 18.0, "currency": "EUR"},
          "duration_minutes": 120,
          "sources": ["https://..."],
          "notes": "Last entry one hour before closing."
        }
      ],
      "exclude": [{"id": "osm:way/1", "reason": "closed for restoration"}],
      "exclude_within": [
        {
          "name": "Roman Forum and Palatine",
          "polygon": [[41.8932, 12.4842], [41.8935, 12.4868], ...],
          "keep": ["osm:relation/1841080"],
          "reason": "inside the ticketed park, visited with the Forum ticket"
        }
      ]
    }

`match.id` pins an entry to one OSM id when the name is ambiguous.

Copies are folded in. OSM often has a second record of a curated place under one of its
names: the Ara Pacis altar next to the Ara Pacis museum, a viewpoint called Giardino degli
Aranci inside the garden. Any record within the entry's radius that carries one of the
entry's names is merged into the curated record, so the planner cannot offer it as a free
extra stop with guessed hours. A venue is never folded into a sight (the San Clemente bar
stays a bar), and a neighbourhood is never folded into anything.

`exclude_within` drops every place inside a polygon (lat, lon corners) except the ids in
`keep`. Big ticketed sites need it: OSM maps each temple of the Forum and each gallery of
the Vatican Museums as its own sight, and without the zone the planner would send someone to
the Temple of Saturn at 9 pm as a free 30 minute stop. A zone never drops a neighbourhood:
the label point of a whole district can fall inside a polygon without the district being
part of the site.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .cost import is_currency_code
from .dedupe import distance_m, is_venue, merge_group
from .hours import parse_opening_hours
from .to_place import normalize_name

DEFAULT_RADIUS_M = 300.0


class CurationError(ValueError):
    """The curation file itself is wrong (bad hours syntax, bad currency, missing field)."""


@dataclass
class CurationReport:
    applied: list[dict] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    excluded_by_zone: dict[str, int] = field(default_factory=dict)
    folded: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "applied": len(self.applied),
            "unmatched": self.unmatched,
            "excluded": self.excluded,
            "excluded_by_zone": self.excluded_by_zone,
            "folded": self.folded,
            "matches": self.applied,
        }


def point_in_polygon(lat: float, lon: float, polygon: list[list[float]]) -> bool:
    """Ray casting test. `polygon` is a list of [lat, lon] corners, first and last not repeated."""
    inside = False
    n = len(polygon)
    for i in range(n):
        lat1, lon1 = polygon[i]
        lat2, lon2 = polygon[(i + 1) % n]
        if (lat1 > lat) != (lat2 > lat):
            cross_lon = lon1 + (lat - lat1) * (lon2 - lon1) / (lat2 - lat1)
            if lon < cross_lon:
                inside = not inside
    return inside


def load_curation(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data.get("places"), list):
        raise CurationError(f"{path}: 'places' must be a list")
    if not data.get("checked_on"):
        raise CurationError(f"{path}: 'checked_on' (YYYY-MM-DD) is required")
    for entry in data["places"]:
        _check_entry(entry)
    for zone in data.get("exclude_within", []):
        if len(zone.get("polygon", [])) < 3 or not zone.get("reason"):
            raise CurationError(f"zone {zone.get('name')!r}: needs a polygon and a reason")
    return data


_CONFIDENCE = {"high", "medium", "low"}


def _check_entry(entry: dict) -> None:
    label = entry.get("name") or "<unnamed entry>"
    if not entry.get("name"):
        raise CurationError("every curated place needs a name")
    if entry.get("confidence", "high") not in _CONFIDENCE:
        raise CurationError(f"{label}: confidence must be high, medium or low")
    if not entry.get("sources"):
        raise CurationError(f"{label}: add at least one source URL")
    hours = entry.get("opening_hours")
    if hours is not None and parse_opening_hours(hours).status != "parsed":
        reason = parse_opening_hours(hours).reason
        raise CurationError(f"{label}: opening_hours {hours!r} cannot be parsed ({reason})")
    price = entry.get("price")
    if price is not None:
        if not is_currency_code(price.get("currency") or ""):
            raise CurationError(f"{label}: price currency must be an ISO 4217 code")
        if not isinstance(price.get("amount"), int | float) or price["amount"] < 0:
            raise CurationError(f"{label}: price amount must be a number >= 0")
    duration = entry.get("duration_minutes")
    if duration is not None and not (isinstance(duration, int) and 5 <= duration <= 1440):
        raise CurationError(f"{label}: duration_minutes must be an integer from 5 to 1440")


def _wanted_names(entry: dict) -> set[str]:
    match = entry.get("match") or {}
    names = [entry["name"], *match.get("names", [])]
    return {normalize_name(n) for n in names if n}


def _names_of(place: dict, signals: dict) -> set[str]:
    return set(signals.get(place["id"], {}).get("names") or []) | {normalize_name(place["name"])}


def _search_area(entry: dict) -> tuple[dict | None, float]:
    match = entry.get("match") or {}
    near = match.get("near")
    point = {"lat": near[0], "lon": near[1]} if near else None
    return point, float(match.get("radius_m", DEFAULT_RADIUS_M))


def _is_neighbourhood(place: dict) -> bool:
    return place["categories"][0] == "neighborhood"


def find_match(entry: dict, places: list[dict], signals: dict) -> dict | None:
    """The place an entry refers to: pinned id, else exact name near the given point."""
    match = entry.get("match") or {}
    if match.get("id"):
        pinned = next((p for p in places if p["id"] == match["id"]), None)
        if pinned is not None:
            return pinned
        # The OSM object was replaced or deleted: fall back to the names below.

    wanted = _wanted_names(entry)
    point, radius = _search_area(entry)

    candidates = []
    for p in places:
        if not _names_of(p, signals) & wanted:
            continue
        dist = distance_m(point, p) if point else 0.0
        if dist <= radius:
            candidates.append((-p.get("popularity", 0.0), dist, p["id"], p))
    if not candidates:
        return None
    # The most popular namesake wins (the Pantheon, not the Bar Pantheon next door),
    # then the closest one.
    candidates.sort(key=lambda c: c[:3])
    return candidates[0][3]


def find_copies(entry: dict, target: dict, places: list[dict], signals: dict) -> list[dict]:
    """Other records of the curated place: one of the entry's names, inside its radius."""
    wanted = _wanted_names(entry)
    point, radius = _search_area(entry)
    point = point or target
    copies = []
    for p in places:
        if p["id"] == target["id"] or is_venue(p) != is_venue(target):
            continue
        if _is_neighbourhood(p) or _is_neighbourhood(target):
            continue
        if _names_of(p, signals) & wanted and distance_m(point, p) <= radius:
            copies.append(p)
    return sorted(copies, key=lambda p: p["id"])


def apply_curation(
    places: list[dict], curation: dict, signals: dict, validator=None
) -> tuple[list[dict], CurationReport]:
    """Return (places with curated facts applied, report). Input records are not mutated."""
    report = CurationReport()
    checked_on = curation["checked_on"]

    drop = {e["id"] for e in curation.get("exclude", []) if e.get("id")}
    for zone in curation.get("exclude_within", []):
        keep = set(zone.get("keep", []))
        inside = {
            p["id"]
            for p in places
            if p["id"] not in keep
            and not _is_neighbourhood(p)
            and point_in_polygon(p["lat"], p["lon"], zone["polygon"])
        }
        report.excluded_by_zone[zone["name"]] = len(inside - drop)
        drop |= inside
    out = [p for p in places if p["id"] not in drop]
    report.excluded = sorted(drop & {p["id"] for p in places})

    # Match every entry before folding anything, so folding the copies of one entry can
    # never remove the place another entry is about.
    matched: list[tuple[dict, dict]] = []
    owner: dict[str, str] = {}
    for entry in curation["places"]:
        target = find_match(entry, out, signals)
        if target is None:
            report.unmatched.append(entry["name"])
            continue
        if target["id"] in owner:
            raise CurationError(
                f"{entry['name']!r} and {owner[target['id']]!r} both match {target['id']}; "
                "pin one of them with match.id"
            )
        owner[target["id"]] = entry["name"]
        matched.append((entry, target))

    by_id = {p["id"]: p for p in out}
    folded: set[str] = set()
    for entry, target in matched:
        copies = [
            c
            for c in find_copies(entry, target, out, signals)
            if c["id"] not in owner and c["id"] not in folded
        ]
        place = merge_group([target, *copies], signals) if copies else dict(target)
        if copies:
            folded.update(c["id"] for c in copies)
            report.folded.append(
                {"entry": entry["name"], "kept": target["id"], "dropped": [c["id"] for c in copies]}
            )
        label = "inferred" if entry.get("confidence") == "low" else "known"
        if entry.get("opening_hours") is not None:
            hours = parse_opening_hours(entry["opening_hours"]).hours
            place["hours"] = {**hours, "confidence": label}
        if entry.get("price") is not None:
            place["cost"] = {
                "amount": float(entry["price"]["amount"]),
                "currency": entry["price"]["currency"],
                "confidence": label,
            }
        if entry.get("duration_minutes") is not None:
            place["typical_duration_minutes"] = int(entry["duration_minutes"])
        place["source"] = "osm+curated"
        place["last_verified"] = entry.get("checked_on", checked_on)
        if validator is not None:
            errors = list(validator.iter_errors(place))
            if errors:
                raise CurationError(f"{entry['name']}: result is not a valid Place: {errors[0]}")
        by_id[place["id"]] = place
        report.applied.append(
            {"name": entry["name"], "id": place["id"], "osm_name": target["name"], "as": label}
        )
    out = [by_id[p["id"]] for p in out if p["id"] not in folded]
    return out, report
