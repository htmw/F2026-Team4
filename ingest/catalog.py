"""Where the rest of the app gets the Lisbon data.

The project plans trips in one city, Lisbon. Its data is committed in data/cities/lisbon/
(rebuilt with make snapshot-lisbon). Other code never opens those files itself. It calls
this module:

    from ingest.catalog import CityNotAvailable, load_city, load_places, travel_legs

    city = load_city("Lisbon")      # CityData: name, destination and places
    places = load_places("Lisboa")  # the same list of places on its own
    legs = travel_legs(places[:50], max_walk_minutes=20)

A name means Lisbon when it is one of the names in city.json (Lisbon, Lisboa, Lisbon,
Portugal...), or one of them followed by the country after a comma (Lisbon, PT). Case,
accents and extra spaces do not matter. Anything else, an empty name, or a different
Lisbon such as Lisbon, Ohio, raises CityNotAvailable. The API turns that into a 422 that
says which city has data, instead of planning a trip somewhere else.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from .matrix import TravelModel
from .matrix import travel_legs as _travel_legs
from .to_place import normalize_name

ROOT = Path(__file__).resolve().parent.parent
CITY_DIR = ROOT / "data" / "cities" / "lisbon"


class CityNotAvailable(LookupError):
    """There is no data for the requested city. The message says which city has data."""


@dataclass(frozen=True)
class CityData:
    key: str  # folder name: lisbon
    name: str  # display name: Lisbon
    destination: dict  # Itinerary destination shape: name, country, lat, lon
    places: list[dict]  # Place records, valid against contracts/place.schema.json


@dataclass(frozen=True)
class _Names:
    full: frozenset[str]  # every name in city.json, normalised: lisbon, lisboa portugal...
    city: frozenset[str]  # the names without a country part: lisbon, lisboa
    country: frozenset[str]  # the country code and name: pt, portugal


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def _load(city_dir: Path) -> tuple[CityData, _Names]:
    """Read the snapshot once per process. Restart the API after a rebuild."""
    meta = _read_json(city_dir / "city.json")
    destination = _read_json(city_dir / "destination.json")
    places = _read_json(city_dir / "places.json")
    all_names = [meta["name"], *meta.get("aliases", [])]
    names = _Names(
        full=frozenset(normalize_name(n) for n in all_names),
        city=frozenset(normalize_name(n) for n in all_names if "," not in n),
        country=frozenset(
            normalize_name(c) for c in (meta.get("country"), meta.get("country_name")) if c
        ),
    )
    return CityData(city_dir.name, destination["name"], destination, places), names


def _is_this_city(name: str, names: _Names) -> bool:
    if normalize_name(name) in names.full:
        return True
    # City, Country: the first part must be the city and the last part its country.
    parts = [p for p in (normalize_name(x) for x in name.split(",")) if p]
    return len(parts) > 1 and parts[0] in names.city and parts[-1] in names.country


def load_city(name: str | None) -> CityData:
    """The Lisbon data, when `name` means Lisbon. Otherwise raises CityNotAvailable."""
    city, names = _load(CITY_DIR)
    if not normalize_name(name or ""):
        raise CityNotAvailable(f"The destination has no name. Cities with data: {city.name}.")
    if not _is_this_city(name, names):
        raise CityNotAvailable(f"No place data for {name!r} yet. Cities with data: {city.name}.")
    return city


def load_places(name: str) -> list[dict]:
    """Shortcut for load_city(name).places. Callers must not change the returned records."""
    return load_city(name).places


def travel_legs(
    places: list[dict], max_walk_minutes: float, model: TravelModel | None = None
) -> dict[tuple[str, str], dict]:
    """Travel time between every ordered pair of the given places, in minutes.

    Returns {(from_id, to_id): {"minutes": 12.4, "mode": "walk"}}. A leg is walk when it
    takes at most max_walk_minutes on foot, otherwise transit. Build it for the candidates
    you are about to schedule, not for the whole city: 300 places give 89,700 legs.
    """
    return _travel_legs(places, max_walk_minutes, model)
