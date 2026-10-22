import pytest

from ingest import catalog


@pytest.mark.parametrize(
    "name",
    [
        "Lisbon",
        "Lisboa",
        "Lisbon, Portugal",
        "Porto",
        "Porto, Portugal",
        "Tbilisi",
        "Madrid",
        "Paris",
        "Rome",
        "New York",
    ],
)
def test_supported_cities_can_be_loaded(name):
    city = catalog.load_city(name)

    assert city.places
    assert city.destination
    assert city.name


@pytest.mark.parametrize(
    "name",
    ["", "Lisbon, Ohio", "Lisboa, Brazil", "Tokyo"],
)
def test_any_other_city_is_refused_with_the_city_that_works(name):
    with pytest.raises(
        catalog.CityNotAvailable,
        match="No place data|destination has no name",
    ):
        catalog.load_city(name)


def test_load_places_returns_city_places():
    places = catalog.load_places("Lisbon")

    assert places
    assert isinstance(places, list)


def test_load_city_returns_expected_city_key():
    city = catalog.load_city("Lisbon")

    assert city.key == "lisbon"
