"""Where the rest of the app gets city data from.

The API and the optimizer should never care whether a city came from a committed snapshot,
from a local ingest run or from the hand-made fixtures. They ask this module:

    city = load_city("Rome")                         # CityData, or CityNotAvailable
    legs = travel_legs(candidates, max_walk_minutes=20)

Lookup order for a destination name, committed data first:
1. data/cities/<key>/   committed snapshots (real OSM data, curated where it matters)
2. fixtures/<key>.places.json   the hand-made sample data (Lisbon)
3. any folder listed in WANDERWISE_EXTRA_CITIES (os.pathsep separated), for trying out a
   local run such as data/out without committing it. Off by default, and it can only add
   cities, never replace a committed one, so a spike run on one laptop never changes what
   the API or the ranker sees for Rome or Lisbon.
4. live from OpenStreetMap, for any other city: see fetch_live(). Set
   WANDERWISE_LIVE_INGEST=0 to turn it off (the tests do, so they never hit the network).

Names match on the city name or an alias ("Rome", "Roma", "Rome, Italy"). "City, Region"
also matches when the last part is the city's country ("Rome, IT", "Rome, Lazio, Italy"),
but "Rome, Georgia" does not: that is a different Rome.

A name OpenStreetMap cannot find, or a country or state instead of a city, raises
CityNotAvailable, so the API can say so instead of quietly planning a trip somewhere else.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import requests

from .cache import slugify
from .geocode import GeocodeError, bbox_span_km, geocode
from .matrix import TravelModel
from .matrix import travel_legs as _travel_legs
from .overpass import QueryTooHeavy
from .pipeline import run_city
from .to_place import normalize_name

ROOT = Path(__file__).resolve().parent.parent
CITIES_DIR = ROOT / "data" / "cities"
EXTRA_DIRS = [Path(p) for p in os.environ.get("WANDERWISE_EXTRA_CITIES", "").split(os.pathsep) if p]
FIXTURES_DIR = ROOT / "fixtures"
LIVE_DIR = ROOT / "data" / "live"
CACHE_DIR = ROOT / "data" / "cache"

LIVE_RADIUS_KM = 5  # fetch the centre of the city, not its whole admin area
LIVE_MAX_AGE_DAYS = 30  # places open and close, so a saved city is fetched again after this
NOT_A_CITY = {"country", "state", "region", "continent"}
# Delhi and Mexico City are states in OpenStreetMap, Singapore is a country: a city-state
# is a few tens of km across, a real state or country is hundreds.
CITY_STATE_MAX_KM = 100

# The tests swap these for fakes.
http_get = requests.get
http_post = requests.post

_live_lock = threading.Lock()

# The hand-made fixtures have no city.json, so their country is written down here.
FIXTURE_COUNTRIES = {"lisbon": ("PT", "Portugal")}


class CityNotAvailable(LookupError):
    """No data for this destination. The message lists the cities that do have data."""


class CityFetchFailed(CityNotAvailable):
    """OpenStreetMap could not be reached. Not the traveler's fault: the API answers 503."""


@dataclass(frozen=True)
class CityData:
    key: str
    name: str
    destination: dict  # Itinerary.destination shape: name, country, lat, lon
    places: list[dict]
    source: str  # snapshot | fixture | local | live
    path: Path
    country_name: str = ""  # "United States", so "Columbia" is not mistaken for Colombia


@dataclass(frozen=True)
class _Entry:
    """One city the catalog can serve, with every name it answers to."""

    key: str
    name: str
    source: str
    path: Path
    names: frozenset[str]  # normalised city names and aliases
    regions: frozenset[str]  # normalised country code, country name, alias regions


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _region_of(alias: str) -> str | None:
    """'Rome, Italy' -> 'italy'. None when the alias has no comma."""
    parts = [normalize_name(p) for p in alias.split(",")]
    parts = [p for p in parts if p]
    return parts[-1] if len(parts) > 1 else None


def _entry(key: str, name: str, source: str, path: Path, aliases, country_bits) -> _Entry:
    aliases = [a for a in aliases if a]
    names = {normalize_name(n) for n in [key.replace("-", " "), name, *aliases]}
    regions = {normalize_name(c) for c in country_bits if c}
    regions.update(r for r in map(_region_of, aliases) if r)
    names.discard("")
    regions.discard("")
    return _Entry(key, name, source, path, frozenset(names), frozenset(regions))


def _dir_entries(base: Path, source: str) -> list[_Entry]:
    if not base.is_dir():
        return []
    out = []
    for d in sorted(x for x in base.iterdir() if (x / "places.json").exists()):
        meta = _read_json(d / "city.json") if (d / "city.json").exists() else {}
        name = meta.get("name") or d.name.replace("-", " ").title()
        country = (meta.get("country", ""), meta.get("country_name", ""))
        out.append(_entry(d.name, name, source, d, meta.get("aliases", []), country))
    return out


def _fixture_entries() -> list[_Entry]:
    out = []
    for f in sorted(FIXTURES_DIR.glob("*.places.json")):
        key = f.name.removesuffix(".places.json")
        country = FIXTURE_COUNTRIES.get(key, ("", ""))
        out.append(_entry(key, key.title(), "fixture", f, [], country))
    return out


def _entries() -> list[_Entry]:
    """Every city in lookup order.

    A later source never serves a city an earlier one already serves, whether the key
    matches (rome) or only the name does (a local run in rome-italy is still Rome).
    """
    seen_keys: set[str] = set()
    served_names: set[str] = set()
    out: list[_Entry] = []
    sources = [
        _dir_entries(CITIES_DIR, "snapshot"),
        _fixture_entries(),
        *(_dir_entries(d, "local") for d in EXTRA_DIRS),
    ]
    for entries in sources:
        for e in entries:
            if e.key in seen_keys or normalize_name(e.name) in served_names:
                continue
            seen_keys.add(e.key)
            served_names.update(e.names)
            out.append(e)
    return out


def available_cities() -> list[dict]:
    """Every city the app can plan for right now, with where its data comes from."""
    return [{"key": e.key, "name": e.name, "source": e.source} for e in _entries()]


def _matches(entry: _Entry, full: str, first: str, region: str | None) -> bool:
    if full in entry.names:
        return True
    return region is not None and first in entry.names and region in entry.regions


def resolve(name: str) -> tuple[str, Path]:
    """Return (source, path) for a destination name, or raise CityNotAvailable."""
    entries = _entries()
    names = ", ".join(e.name for e in entries) or "none yet"
    full = normalize_name(name or "")
    if not full:
        raise CityNotAvailable(f"The destination has no name. Cities with data: {names}.")
    parts = [p for p in (normalize_name(x) for x in name.split(",")) if p]
    first = parts[0]
    region = parts[-1] if len(parts) > 1 else None
    for e in entries:
        if _matches(e, full, first, region):
            return e.source, e.path
    if os.environ.get("WANDERWISE_LIVE_INGEST", "1") != "0":
        return "live", fetch_live(name)
    raise CityNotAvailable(f"No place data for {name!r} yet. Cities with data: {names}.")


def fetch_live(name: str) -> Path:
    """Fetch a city from OpenStreetMap and keep it in data/live/<city>-<country>/.

    Only the first request for a city waits; later ones read the folder. The folder is named
    after what OpenStreetMap found, so "Paris" and "Paris, France" share one, and
    "Paris, Texas" gets its own. One fetch at a time, because Overpass rate limits hard.
    """
    with _live_lock:
        try:
            geo = geocode(name, CACHE_DIR, get=http_get, max_span_km=None)
        except GeocodeError as exc:
            raise CityNotAvailable(str(exc)) from exc
        except requests.RequestException as exc:
            raise CityFetchFailed(f"Could not reach OpenStreetMap to look up {name!r}.") from exc
        if geo.kind in NOT_A_CITY and max(bbox_span_km(geo.bbox)) > CITY_STATE_MAX_KM:
            raise CityNotAvailable(f"{name!r} is a {geo.kind}, not a city. Pick a city in it.")

        folder = LIVE_DIR / slugify(f"{geo.name}-{geo.country}")
        saved = folder / "places.json"
        if saved.exists() and time.time() - saved.stat().st_mtime < LIVE_MAX_AGE_DAYS * 86400:
            return folder

        # Fetch into a side folder and swap it in only when it holds places, so a failed or
        # empty refresh never costs the copy a traveler could still use.
        incoming = LIVE_DIR / ".incoming"
        shutil.rmtree(incoming / folder.name, ignore_errors=True)

        def fetch(radius_km: float) -> dict:
            return run_city(
                name,
                cache_dir=CACHE_DIR,
                out_dir=incoming,
                contracts_dir=ROOT / "contracts",
                bbox=geo.box_around_centre(radius_km),
                slug=folder.name,
                matrix_top=0,
                combine_groups=True,
                post=http_post,
                get=http_get,
                sleep=time.sleep,  # looked up now, so tests can skip the pauses
                refresh=saved.exists(),  # an old city must not come back from the raw cache
            )

        try:
            try:
                result = fetch(LIVE_RADIUS_KM)
            except QueryTooHeavy:
                # Central London is too much for one query. Its middle still fills a trip.
                result = fetch(LIVE_RADIUS_KM / 2)
        except (RuntimeError, requests.RequestException) as exc:
            if saved.exists():
                return folder  # an old copy beats no trip; the next request tries again
            raise CityFetchFailed(f"Could not fetch {name!r} from OpenStreetMap: {exc}") from exc

        if not result["places"]:
            shutil.rmtree(result["out_dir"])
            if saved.exists():
                return folder  # keep the old copy; the next request tries again
            raise CityNotAvailable(f"OpenStreetMap has no places mapped in {geo.display_name}.")
        shutil.rmtree(folder, ignore_errors=True)
        shutil.move(str(result["out_dir"]), str(folder))
        return folder


@lru_cache(maxsize=16)
def _load(source: str, path: Path, mtime: float) -> CityData:
    if source == "fixture":
        places = _read_json(path)
        key = path.name.removesuffix(".places.json")
        lat = sum(p["lat"] for p in places) / len(places)
        lon = sum(p["lon"] for p in places) / len(places)
        destination = {"name": key.title(), "lat": round(lat, 4), "lon": round(lon, 4)}
        country_code, country_name = FIXTURE_COUNTRIES.get(key, ("", ""))
        if country_code:
            destination["country"] = country_code
        return CityData(key, key.title(), destination, places, source, path, country_name)
    places = _read_json(path / "places.json")
    destination = _read_json(path / "destination.json")
    meta = _read_json(path / "city.json") if (path / "city.json").exists() else {}
    country_name = meta.get("country_name", "")
    return CityData(path.name, destination["name"], destination, places, source, path, country_name)


def load_city(name: str | None) -> CityData:
    """Places and destination info for a city name such as 'Rome' or 'Rome, Italy'."""
    source, path = resolve(name or "")
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
    300 places is 89,700 legs and takes about 0.1 s, most of it building the dict.
    """
    return _travel_legs(places, max_walk_minutes, model)
