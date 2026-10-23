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
4. live from OpenStreetMap: any other city is geocoded with Nominatim, fetched from
   Overpass (one combined query for the area around the centre) and run through the same
   pipeline. The result is saved in data/live/<name>-<country>/ (git-ignored) and reused
   for LIVE_MAX_AGE_DAYS, so only the first traveler to ask for a city waits for the fetch.
   Live folders are keyed by what Nominatim resolved the name to, so "Paris" and
   "Paris, France" share one folder and "Paris, Texas" gets its own.
   Set WANDERWISE_LIVE_INGEST=0 to turn this off (the tests do, so they never hit the network).

Names match on the city name or an alias ("Rome", "Roma", "Rome, Italy"). "City, Region"
also matches when the last part is the city's country ("Rome, IT", "Rome, Lazio, Italy"),
but "Rome, Georgia" does not: that is a different Rome.

A name OpenStreetMap cannot place, a whole region or country, or a place with no sights
raises CityNotAvailable, so the API can say so instead of quietly planning a trip somewhere
else. When OpenStreetMap cannot be reached, CityFetchFailed (a CityNotAvailable) says so.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import requests

from .cache import slugify
from .geocode import GeocodeError, clip_bbox, geocode
from .matrix import TravelModel
from .matrix import travel_legs as _travel_legs
from .pipeline import run_city
from .to_place import normalize_name

ROOT = Path(__file__).resolve().parent.parent
CITIES_DIR = ROOT / "data" / "cities"
EXTRA_DIRS = [Path(p) for p in os.environ.get("WANDERWISE_EXTRA_CITIES", "").split(os.pathsep) if p]
FIXTURES_DIR = ROOT / "fixtures"
LIVE_DIR = ROOT / "data" / "live"
CACHE_DIR = ROOT / "data" / "cache"
CONTRACTS_DIR = ROOT / "contracts"

# Live fetch: the walkable middle of the city, refreshed once a month.
LIVE_RADIUS_KM = 6.0
LIVE_MAX_AGE_DAYS = 30

# The HTTP functions the live fetch uses. Tests swap them for fakes.
http_get = requests.get
http_post = requests.post

log = logging.getLogger(__name__)
_live_lock = threading.Lock()

# The hand-made fixtures have no city.json, so their country is written down here.
FIXTURE_COUNTRIES = {"lisbon": ("PT", "Portugal")}


class CityNotAvailable(LookupError):
    """No data for this destination. The message lists the cities that do have data."""


class CityFetchFailed(CityNotAvailable):
    """The city may well exist, but OpenStreetMap could not be reached to fetch it."""


def live_enabled() -> bool:
    """Live fetching is on unless WANDERWISE_LIVE_INGEST is 0, false, no or off."""
    value = os.environ.get("WANDERWISE_LIVE_INGEST", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class CityData:
    key: str
    name: str
    destination: dict  # Itinerary.destination shape: name, country, lat, lon
    places: list[dict]
    source: str  # snapshot | fixture | local
    path: Path


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
    if live_enabled():
        return "live", fetch_live(name)
    raise CityNotAvailable(f"No place data for {name!r} yet. Cities with data: {names}.")


def _fresh(path: Path) -> bool:
    places = path / "places.json"
    return places.exists() and time.time() - places.stat().st_mtime < LIVE_MAX_AGE_DAYS * 86400


def fetch_live(name: str) -> Path:
    """Fetch a city from OpenStreetMap, or reuse a recent fetch. Returns its folder.

    One fetch at a time: Overpass rate limits hard, and two travelers asking for the same
    new city at once should cost one fetch, not two.
    """
    with _live_lock:
        try:
            geo = geocode(name, CACHE_DIR, get=http_get)
        except GeocodeError as exc:
            raise CityNotAvailable(f"Could not plan for {name!r}: {exc}") from exc
        except requests.RequestException as exc:
            raise CityFetchFailed(
                f"Could not reach OpenStreetMap to look up {name!r}. Try again in a minute."
            ) from exc

        slug = slugify(f"{geo.name}-{geo.country}" if geo.country else geo.name)
        path = LIVE_DIR / slug
        if _fresh(path):
            return path

        bbox = clip_bbox(geo.bbox, geo.lat, geo.lon, LIVE_RADIUS_KM)
        log.info("live ingest: %r -> %s, bbox %s", name, geo.display_name, bbox)
        try:
            result = run_city(
                name,
                cache_dir=CACHE_DIR,
                out_dir=LIVE_DIR,
                contracts_dir=CONTRACTS_DIR,
                bbox=bbox,
                slug=slug,
                matrix_top=0,  # the scheduler builds legs for its candidates on demand
                combine_groups=True,
                post=http_post,
                get=http_get,
                log=log.info,
            )
        except (RuntimeError, requests.RequestException) as exc:
            raise CityFetchFailed(
                f"Could not fetch places for {name!r} from OpenStreetMap: {exc}"
            ) from exc

        if not result["places"]:
            raise CityNotAvailable(
                f"OpenStreetMap has no sights, food or parks mapped around {geo.display_name!r}."
            )
        return path


@lru_cache(maxsize=16)
def _load(source: str, path: Path, mtime: float) -> CityData:
    if source == "fixture":
        places = _read_json(path)
        key = path.name.removesuffix(".places.json")
        lat = sum(p["lat"] for p in places) / len(places)
        lon = sum(p["lon"] for p in places) / len(places)
        destination = {"name": key.title(), "lat": round(lat, 4), "lon": round(lon, 4)}
        country = FIXTURE_COUNTRIES.get(key, ("", ""))[0]
        if country:
            destination["country"] = country
        return CityData(key, key.title(), destination, places, source, path)
    places = _read_json(path / "places.json")
    destination = _read_json(path / "destination.json")
    return CityData(path.name, destination["name"], destination, places, source, path)


def load_city(name: str | None) -> CityData:
    """Places and destination info for a city name such as 'Rome' or 'Rome, Italy'."""
    source, path = resolve(name or "")
    stamp_file = path if source == "fixture" else path / "places.json"
    # The stamp makes a refreshed live fetch replace the cached CityData.
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
