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

`exclude_within` drops every place inside a polygon (lat, lon corners) except the ids in
`keep`. Big ticketed sites need it: OSM maps each temple of the Forum and each gallery of
the Vatican Museums as its own sight, and without the zone the planner would send someone to
the Temple of Saturn at 9 pm as a free 30 minute stop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .cost import is_currency_code
from .dedupe import distance_m
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

    def as_dict(self) -> dict:
        return {
            "applied": len(self.applied),
            "unmatched": self.unmatched,
            "excluded": self.excluded,
            "excluded_by_zone": self.excluded_by_zone,
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


def find_match(entry: dict, places: list[dict], signals: dict) -> dict | None:
    """The place an entry refers to: pinned id, else exact name near the given point."""
    match = entry.get("match") or {}
    if match.get("id"):
        pinned = next((p for p in places if p["id"] == match["id"]), None)
        if pinned is not None:
            return pinned
        # The OSM object was replaced or deleted: fall back to the names below.

    wanted = _wanted_names(entry)
    near = match.get("near")
    radius = float(match.get("radius_m", DEFAULT_RADIUS_M))
    point = {"lat": near[0], "lon": near[1]} if near else None

    candidates = []
    for p in places:
        names = set(signals.get(p["id"], {}).get("names") or [normalize_name(p["name"])])
        if not names & wanted:
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
            if p["id"] not in keep and point_in_polygon(p["lat"], p["lon"], zone["polygon"])
        }
        report.excluded_by_zone[zone["name"]] = len(inside - drop)
        drop |= inside
    out = [p for p in places if p["id"] not in drop]
    report.excluded = sorted(drop & {p["id"] for p in places})

    index = {p["id"]: i for i, p in enumerate(out)}
    for entry in curation["places"]:
        target = find_match(entry, out, signals)
        if target is None:
            report.unmatched.append(entry["name"])
            continue
        place = dict(target)
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
        out[index[place["id"]]] = place
        report.applied.append(
            {"name": entry["name"], "id": place["id"], "osm_name": target["name"], "as": label}
        )
    return out, report
