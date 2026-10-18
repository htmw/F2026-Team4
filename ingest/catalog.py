"""Where the rest of the app gets city data from.

The API and the optimizer should never care whether a city came from a committed snapshot,
from a local ingest run or from the hand-made fixtures. They ask this module:

    city = load_city("Rome")                         # CityData, or CityNotAvailable
    legs = travel_legs(candidates, max_walk_minutes=20)

Lookup order for a destination name:
1. data/cities/<key>/   committed snapshots (real OSM data, curated where it matters)
2. any folder listed in WANDERWISE_EXTRA_CITIES (os.pathsep separated), for trying out a
   local run such as data/out without committing it. Off by default, so a spike run on
   one laptop never changes what the API or the ranker sees on another.
3. fixtures/<key>.places.json   the hand-made sample data (Lisbon)

A name nobody has data for raises CityNotAvailable with the list of cities that do work,
so the API can say so instead of quietly planning a trip somewhere else.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .matrix import TravelModel
from .matrix import travel_legs as _travel_legs
from .to_place import normalize_name

ROOT = Path(__file__).resolve().parent.parent
CITIES_DIR = ROOT / "data" / "cities"
EXTRA_DIRS = [Path(p) for p in os.environ.get("WANDERWISE_EXTRA_CITIES", "").split(os.pathsep) if p]
FIXTURES_DIR = ROOT / "fixtures"


class CityNotAvailable(LookupError):
    """No data for this destination. The message lists the cities that do have data."""


@dataclass(frozen=True)
class CityData:
    key: str
    name: str
    destination: dict  # Itinerary.destination shape: name, country, lat, lon
    places: list[dict]
    source: str  # snapshot | local | fixture
    path: Path


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _city_dirs(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return sorted(d for d in base.iterdir() if (d / "places.json").exists())


def _names_for_dir(city_dir: Path) -> set[str]:
    names = {city_dir.name.replace("-", " ")}
    meta_file = city_dir / "city.json"
    if meta_file.exists():
        meta = _read_json(meta_file)
        names.update([meta.get("name", ""), *meta.get("aliases", [])])
    return {normalize_name(n) for n in names if n}


def _fixture_files() -> list[Path]:
    return sorted(FIXTURES_DIR.glob("*.places.json"))


def _candidates(name: str) -> list[str]:
    """'Rome, Italy' -> ['rome italy', 'rome']. Exact form first, then the part before a comma."""
    full = normalize_name(name)
    first = normalize_name(name.split(",")[0])
    return [n for n in dict.fromkeys([full, first]) if n]


def _sources() -> list[tuple[str, Path]]:
    return [("snapshot", CITIES_DIR), *(("local", d) for d in EXTRA_DIRS)]


def available_cities() -> list[dict]:
    """Every city the app can plan for right now, with where its data comes from."""
    seen: set[str] = set()
    out: list[dict] = []
    for source, base in _sources():
        for d in _city_dirs(base):
            if d.name in seen:
                continue
            seen.add(d.name)
            meta = _read_json(d / "city.json") if (d / "city.json").exists() else {}
            out.append({"key": d.name, "name": meta.get("name", d.name.title()), "source": source})
    for f in _fixture_files():
        key = f.name.removesuffix(".places.json")
        if key not in seen:
            seen.add(key)
            out.append({"key": key, "name": key.title(), "source": "fixture"})
    return out


def resolve(name: str) -> tuple[str, Path]:
    """Return (source, path) for a destination name, or raise CityNotAvailable."""
    wanted = _candidates(name or "")
    for source, base in _sources():
        dirs = _city_dirs(base)
        for candidate in wanted:
            for d in dirs:
                if candidate in _names_for_dir(d):
                    return source, d
    for candidate in wanted:
        for f in _fixture_files():
            if normalize_name(f.name.removesuffix(".places.json")) == candidate:
                return "fixture", f
    names = ", ".join(c["name"] for c in available_cities()) or "none yet"
    raise CityNotAvailable(f"No place data for {name!r} yet. Cities with data: {names}.")


@lru_cache(maxsize=16)
def _load(source: str, path: Path, mtime: float) -> CityData:
    if source == "fixture":
        places = _read_json(path)
        key = path.name.removesuffix(".places.json")
        lat = sum(p["lat"] for p in places) / len(places)
        lon = sum(p["lon"] for p in places) / len(places)
        destination = {"name": key.title(), "lat": round(lat, 4), "lon": round(lon, 4)}
        return CityData(key, key.title(), destination, places, source, path)
    places = _read_json(path / "places.json")
    destination = _read_json(path / "destination.json")
    return CityData(path.name, destination["name"], destination, places, source, path)


def load_city(name: str) -> CityData:
    """Places and destination info for a city name such as 'Rome' or 'Rome, Italy'."""
    source, path = resolve(name)
    stamp_file = path if source == "fixture" else path / "places.json"
    return _load(source, path, stamp_file.stat().st_mtime)


def load_places(name: str) -> list[dict]:
    """Shortcut for load_city(name).places. Callers must not mutate the returned records."""
    return load_city(name).places


def travel_legs(
    places: list[dict], max_walk_minutes: float, model: TravelModel | None = None
) -> dict[tuple[str, str], dict]:
    """Legs between every pair of the given places, in the optimizer's matrix shape.

    Build it for the candidate list you are about to schedule, not for a whole city:
    300 places is 89,700 legs and takes a few milliseconds.
    """
    return _travel_legs(places, max_walk_minutes, model)
