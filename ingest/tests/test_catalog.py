"""Tests for the catalog: the one place the app reads the Lisbon data from."""

import json
from pathlib import Path

import pytest

from ingest import catalog
from ingest.to_place import make_validator

ROOT = Path(__file__).resolve().parents[2]
LISBON_DIR = ROOT / "data" / "cities" / "lisbon"


@pytest.mark.parametrize(
    "name",
    [
        "Lisbon",
        "lisbon",
        "  LISBOA ",
        "Lisbon, Portugal",
        "Lisboa, Portugal",
        "Lisbon Portugal",
        "Lisbon, PT",
        "Lisbon, Lisbon District, Portugal",
    ],
)
def test_every_way_of_naming_lisbon_gets_the_lisbon_data(name):
    city = catalog.load_city(name)

    assert city.key == "lisbon"
    assert city.name == "Lisbon"
    assert city.destination["country"] == "PT"


@pytest.mark.parametrize("name", ["Lisbon, Ohio", "Lisboa, Brazil", "Rome", "Porto"])
def test_any_other_city_is_refused_with_the_city_that_works(name):
    with pytest.raises(catalog.CityNotAvailable, match="No place data.*Cities with data: Lisbon"):
        catalog.load_city(name)


@pytest.mark.parametrize("name", ["", "   ", None, ","])
def test_a_missing_name_is_refused(name):
    with pytest.raises(catalog.CityNotAvailable, match="no name.*Lisbon"):
        catalog.load_city(name)


def test_lisbon_is_the_real_osm_snapshot():
    city = catalog.load_city("Lisbon")

    assert len(city.places) > 5000
    assert all(p["id"].startswith("osm:") for p in city.places)
    assert 38.6 < city.destination["lat"] < 38.8
    assert catalog.load_places("Lisboa") is city.places


def test_travel_legs_cover_every_ordered_pair():
    places = catalog.load_places("Lisbon")[:4]

    legs = catalog.travel_legs(places, max_walk_minutes=15)

    assert len(legs) == 12
    assert all(leg["mode"] in {"walk", "transit"} for leg in legs.values())
    assert all(leg["minutes"] > 0 for leg in legs.values())


def test_the_lisbon_snapshot_is_complete_and_valid():
    """Every place passes the Place contract, ids are unique and every place is in the box."""
    for name in ("places.json", "destination.json", "city.json", "report.json"):
        assert (LISBON_DIR / name).exists(), name
    places = json.loads((LISBON_DIR / "places.json").read_text(encoding="utf-8"))
    south, west, north, east = json.loads((LISBON_DIR / "city.json").read_text())["bbox"]
    validator = make_validator(ROOT / "contracts" / "place.schema.json")

    ids = [p["id"] for p in places]
    assert len(ids) == len(set(ids)), "duplicate ids"
    for place in places:
        errors = list(validator.iter_errors(place))
        assert not errors, f"{place['id']}: {errors[0].message}"
        assert south <= place["lat"] <= north and west <= place["lon"] <= east, place["id"]
