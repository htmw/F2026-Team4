"""Tests for the city catalog the API reads places from."""

import json
from pathlib import Path

import pytest

from ingest import catalog
from ingest.to_place import make_validator

ROOT = Path(__file__).resolve().parents[2]


def _hours():
    hours = {d: [["09:00", "18:00"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
    hours["confidence"] = "inferred"
    return hours


def _write_city(base: Path, key: str, name: str, aliases=(), n=3):
    d = base / key
    d.mkdir(parents=True)
    places = [
        {
            "id": f"osm:node/{i}",
            "name": f"{name} place {i}",
            "lat": 41.9 + i * 0.001,
            "lon": 12.5,
            "categories": ["museum"],
            "typical_duration_minutes": 60,
            "cost": {"amount": 0.0, "currency": "EUR", "confidence": "unknown"},
            "hours": _hours(),
            "source": "osm",
        }
        for i in range(n)
    ]
    (d / "places.json").write_text(json.dumps(places), encoding="utf-8")
    (d / "destination.json").write_text(
        json.dumps({"name": name, "country": "IT", "lat": 41.9, "lon": 12.5}), encoding="utf-8"
    )
    (d / "city.json").write_text(
        json.dumps({"key": key, "name": name, "aliases": list(aliases)}), encoding="utf-8"
    )
    return d


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    cities, out = tmp_path / "cities", tmp_path / "out"
    cities.mkdir()
    out.mkdir()
    monkeypatch.setattr(catalog, "CITIES_DIR", cities)
    monkeypatch.setattr(catalog, "EXTRA_DIRS", [])
    return cities, out


@pytest.mark.parametrize("name", ["Rome", "rome", "Rome, Italy", "ROMA", "  roma "])
def test_snapshot_found_by_name_alias_or_city_country(dirs, name):
    cities, _ = dirs
    _write_city(cities, "rome", "Rome", aliases=["Roma", "Rome, Italy"])
    city = catalog.load_city(name)

    assert city.key == "rome"
    assert city.source == "snapshot"
    assert city.destination["country"] == "IT"
    assert len(city.places) == 3


def test_local_runs_are_ignored_unless_asked_for(dirs, monkeypatch):
    _, out = dirs
    _write_city(out, "porto-portugal", "Porto", aliases=["Porto, Portugal"])

    with pytest.raises(catalog.CityNotAvailable):
        catalog.load_city("Porto")

    monkeypatch.setattr(catalog, "EXTRA_DIRS", [out])
    city = catalog.load_city("Porto")

    assert city.source == "local"
    assert city.name == "Porto"


def test_snapshot_beats_local_output_for_the_same_city(dirs, monkeypatch):
    cities, out = dirs
    _write_city(cities, "rome", "Rome")
    _write_city(out, "rome", "Rome", n=1)
    monkeypatch.setattr(catalog, "EXTRA_DIRS", [out])

    assert catalog.load_city("Rome").source == "snapshot"


def test_fixture_city_still_works(dirs):
    city = catalog.load_city("Lisbon")

    assert city.source == "fixture"
    assert city.places[0]["id"].startswith("fixture:")
    assert 38.6 < city.destination["lat"] < 38.8


def test_unknown_city_says_which_cities_work(dirs):
    cities, _ = dirs
    _write_city(cities, "rome", "Rome")

    with pytest.raises(catalog.CityNotAvailable, match="New York.*Rome.*Lisbon"):
        catalog.load_city("New York")


def test_available_cities_lists_each_city_once(dirs, monkeypatch):
    cities, out = dirs
    _write_city(cities, "rome", "Rome")
    _write_city(out, "rome", "Rome")
    monkeypatch.setattr(catalog, "EXTRA_DIRS", [out])

    listed = catalog.available_cities()

    assert [c["key"] for c in listed] == ["rome", "lisbon"]
    assert listed[0]["source"] == "snapshot"


def test_travel_legs_cover_every_ordered_pair(dirs):
    cities, _ = dirs
    _write_city(cities, "rome", "Rome", n=4)
    places = catalog.load_places("Rome")

    legs = catalog.travel_legs(places, max_walk_minutes=15)

    assert len(legs) == 12
    assert {leg["mode"] for leg in legs.values()} == {"walk"}


def test_committed_snapshots_are_valid_places():
    """Every snapshot in data/cities must pass the Place contract and carry its metadata."""
    validator = make_validator(ROOT / "contracts" / "place.schema.json")
    for city_dir in sorted((ROOT / "data" / "cities").glob("*/")):
        places = json.loads((city_dir / "places.json").read_text(encoding="utf-8"))
        assert places, f"{city_dir.name}: empty snapshot"
        assert (city_dir / "destination.json").exists()
        assert (city_dir / "city.json").exists()
        ids = [p["id"] for p in places]
        assert len(ids) == len(set(ids)), f"{city_dir.name}: duplicate ids"
        for place in places:
            errors = list(validator.iter_errors(place))
            assert not errors, f"{city_dir.name} {place['id']}: {errors[0].message}"
