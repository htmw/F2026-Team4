"""Tests for converting OSM elements into Place records."""

from pathlib import Path

import pytest

from ingest.to_place import build_place, make_validator


@pytest.fixture
def validator():
    schema_path = Path(__file__).resolve().parents[2] / "contracts" / "place.schema.json"
    return make_validator(schema_path)


def test_build_place_creates_valid_museum(validator):
    element = {
        "type": "node",
        "id": 123,
        "lat": 51.5072,
        "lon": -0.1276,
        "tags": {"name": "British Museum", "tourism": "museum"},
    }

    result = build_place(
        element,
        currency="GBP",
        fetched_date="2026-10-14",
        validator=validator,
    )

    assert result.place is not None
    assert result.drop_reason is None
    assert result.place["id"] == "osm:node/123"
    assert result.place["name"] == "British Museum"
    assert result.place["lat"] == pytest.approx(51.5072)
    assert result.place["lon"] == pytest.approx(-0.1276)
    assert result.place["categories"] == ["museum"]
    assert result.place["typical_duration_minutes"] == 90
    assert result.place["hours"]["confidence"] == "inferred"
    assert result.place["source"] == "osm"
    assert result.place["last_verified"] == "2026-10-14"


def test_build_place_rejects_missing_name(validator):
    result = build_place(
        {"type": "node", "id": 1, "lat": 1.0, "lon": 2.0, "tags": {}},
        currency="USD",
        fetched_date="2026-10-14",
        validator=validator,
    )

    assert result.place is None
    assert result.drop_reason == "no_name"


def test_build_place_rejects_missing_coordinates(validator):
    result = build_place(
        {"type": "node", "id": 2, "tags": {"name": "Museum", "tourism": "museum"}},
        currency="USD",
        fetched_date="2026-10-14",
        validator=validator,
    )

    assert result.place is None
    assert result.drop_reason == "no_coords"


def test_build_place_uses_center_for_way_coordinates(validator):
    element = {
        "type": "way",
        "id": 3,
        "center": {"lat": 40.7, "lon": -74.0},
        "tags": {"name": "City Museum", "tourism": "museum"},
    }

    result = build_place(
        element,
        currency="USD",
        fetched_date="2026-10-14",
        validator=validator,
    )

    assert result.place is not None
    assert result.place["id"] == "osm:way/3"
    assert result.place["lat"] == pytest.approx(40.7)
    assert result.place["lon"] == pytest.approx(-74.0)


def test_build_place_rejects_unmapped_category(validator):
    result = build_place(
        {
            "type": "node",
            "id": 4,
            "lat": 1.0,
            "lon": 2.0,
            "tags": {"name": "Unknown Place"},
        },
        currency="USD",
        fetched_date="2026-10-14",
        validator=validator,
    )

    assert result.place is None
    assert result.drop_reason == "unmapped_category"


def test_build_place_rejects_schema_invalid_coordinates(validator):
    result = build_place(
        {
            "type": "node",
            "id": 5,
            "lat": 100.0,
            "lon": 2.0,
            "tags": {"name": "Museum", "tourism": "museum"},
        },
        currency="USD",
        fetched_date="2026-10-14",
        validator=validator,
    )

    assert result.place is None
    assert result.drop_reason == "schema_invalid"
    assert result.error is not None


def test_restaurant_closed_on_one_day_is_kept_with_unknown_hours(validator):
    result = build_place(
        {
            "type": "node",
            "id": 6,
            "lat": 41.89,
            "lon": 12.47,
            "tags": {"name": "Trattoria", "amenity": "restaurant", "opening_hours": "Su off"},
        },
        currency="EUR",
        fetched_date="2026-10-17",
        validator=validator,
    )

    assert result.place is not None
    assert result.place["hours"]["confidence"] == "unknown"


def test_place_closed_every_day_is_dropped(validator):
    result = build_place(
        {
            "type": "node",
            "id": 7,
            "lat": 41.89,
            "lon": 12.47,
            "tags": {"name": "Museo Chiuso", "tourism": "museum", "opening_hours": "off"},
        },
        currency="EUR",
        fetched_date="2026-10-17",
        validator=validator,
    )

    assert result.place is None
    assert result.drop_reason == "always_closed"


@pytest.mark.parametrize(
    "el_type, tags, long_structure, rough_point",
    [
        ("way", {"historic": "citywalls", "barrier": "city_wall"}, True, False),
        ("way", {"historic": "aqueduct"}, True, False),
        ("relation", {"historic": "citywalls", "type": "building"}, True, True),
        ("relation", {"historic": "citywalls", "type": "site"}, True, True),
        ("relation", {"historic": "aqueduct", "type": "waterway"}, True, True),
        ("relation", {"historic": "citywalls", "type": "multipolygon"}, True, False),
        ("way", {"historic": "ruins", "wikidata": "Q1"}, False, False),
    ],
)
def test_signals_mark_wall_pieces_and_collection_relations(
    validator, el_type, tags, long_structure, rough_point
):
    element = {
        "type": el_type,
        "id": 8,
        "center": {"lat": 41.89, "lon": 12.49},
        "tags": {"name": "Mura Aureliane", **tags},
    }
    result = build_place(element, currency="EUR", fetched_date="2026-10-17", validator=validator)

    assert result.signals["long_structure"] is long_structure
    assert result.signals["rough_point"] is rough_point


def _build(tags, validator):
    element = {"type": "node", "id": 1, "lat": 18.43, "lon": 79.13, "tags": tags}
    return build_place(element, currency="INR", fetched_date="2026-10-24", validator=validator)


def test_a_school_tagged_as_a_sight_is_left_out(validator):
    karimnagar = {"name": "sree chaitanya clg", "tourism": "viewpoint", "college": "scce"}
    result = _build(karimnagar, validator)

    assert result.place is None
    assert result.drop_reason == "school"
    school = {"name": "A School", "tourism": "attraction", "amenity": "school"}
    assert _build(school, validator).place is None


def test_a_famous_university_stays(validator):
    coimbra = {"name": "Universidade de Coimbra", "tourism": "attraction",
               "amenity": "university", "wikidata": "Q368643"}

    assert _build(coimbra, validator).place is not None


@pytest.mark.parametrize(
    "tags",
    [
        {"name": "Sabji Market", "amenity": "marketplace"},
        {"name": "Footware market", "amenity": "marketplace"},
        {"name": "Plaque", "historic": "memorial", "tourism": "attraction"},
        {"name": "Some Hill View", "tourism": "viewpoint"},
    ],
)
def test_an_unknown_market_landmark_or_viewpoint_is_left_out(validator, tags):
    result = _build(tags, validator)

    assert result.place is None
    assert result.drop_reason == "not_famous"


@pytest.mark.parametrize(
    "tags",
    [
        {"name": "Crawford Market", "amenity": "marketplace", "wikidata": "Q3631430"},
        {"name": "Gateway of India", "tourism": "attraction", "wikidata": "Q190711"},
        {"name": "Local History Museum", "tourism": "museum"},
        {"name": "Sharma Dhaba", "amenity": "restaurant"},
        {"name": "Old City Wall", "historic": "citywalls"},
    ],
)
def test_famous_places_typed_sights_venues_and_wall_pieces_stay(validator, tags):
    assert _build(tags, validator).place is not None
