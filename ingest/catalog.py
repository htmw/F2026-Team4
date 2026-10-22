"""Load committed city snapshots for the Wanderwise app."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from .matrix import TravelModel
from .matrix import travel_legs as _travel_legs
from .to_place import normalize_name

ROOT = Path(__file__).resolve().parent.parent
CITY_ROOT = ROOT / "data" / "cities"


class CityNotAvailable(LookupError):
    """Raised when the requested city has no committed data."""


@dataclass(frozen=True)
class CityData:
    key: str
    name: str
    destination: dict
    places: list[dict]


@dataclass(frozen=True)
class _Names:
    full: frozenset[str]
    city: frozenset[str]
    country: frozenset[str]


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _make_names(meta: dict) -> _Names:
    all_names = [meta["name"], *meta.get("aliases", [])]
    return _Names(
        full=frozenset(normalize_name(n) for n in all_names),
        city=frozenset(
            normalize_name(n) for n in all_names if "," not in n
        ),
        country=frozenset(
            normalize_name(c)
            for c in (meta.get("country"), meta.get("country_name"))
            if c
        ),
    )


@cache
def _load(city_dir: Path) -> tuple[CityData, _Names]:
    """Read one city snapshot once per process."""
    meta = _read_json(city_dir / "city.json")
    destination = _read_json(city_dir / "destination.json")
    places = _read_json(city_dir / "places.json")

    return (
        CityData(
            key=city_dir.name,
            name=destination["name"],
            destination=destination,
            places=places,
        ),
        _make_names(meta),
    )


@cache
def _city_entries() -> tuple[tuple[Path, _Names, str], ...]:
    """Discover city snapshots in data/cities."""
    if not CITY_ROOT.is_dir():
        return ()

    entries = []
    required = ("city.json", "destination.json", "places.json")

    for city_dir in sorted(CITY_ROOT.iterdir()):
        if not city_dir.is_dir():
            continue

        if not all((city_dir / filename).is_file() for filename in required):
            continue

        meta = _read_json(city_dir / "city.json")
        entries.append((city_dir, _make_names(meta), meta["name"]))

    return tuple(entries)


def _is_this_city(name: str, names: _Names) -> bool:
    normalized = normalize_name(name)

    if normalized in names.full:
        return True

    parts = [
        normalize_name(part)
        for part in name.split(",")
        if normalize_name(part)
    ]

    return (
        len(parts) > 1
        and parts[0] in names.city
        and parts[-1] in names.country
    )


def _available_names() -> str:
    names = [entry[2] for entry in _city_entries()]
    return ", ".join(names) if names else "none"


def load_city(name: str | None) -> CityData:
    """Load a supported city or raise CityNotAvailable."""
    if not normalize_name(name or ""):
        raise CityNotAvailable(
            f"The destination has no name. Cities with data: "
            f"{_available_names()}."
        )

    for city_dir, names, _display_name in _city_entries():
        if _is_this_city(name, names):
            return _load(city_dir)[0]

    raise CityNotAvailable(
        f"No place data for {name!r} yet. "
        f"Cities with data: {_available_names()}."
    )


def load_places(name: str) -> list[dict]:
    """Return the places for a supported city."""
    return load_city(name).places


def travel_legs(
    places: list[dict],
    max_walk_minutes: float,
    model: TravelModel | None = None,
) -> dict[tuple[str, str], dict]:
    """Calculate travel legs between candidate places."""
    return _travel_legs(places, max_walk_minutes, model)
