"""Tests for mapping OSM tags to controlled categories."""

from pathlib import Path

from ingest.categories import (
    check_against_vocabulary,
    load_vocabulary,
    map_categories,
    mapped_categories,
    unmapped_vocabulary,
)

CATEGORIES_FILE = Path(__file__).resolve().parents[2] / "contracts" / "categories.json"


def test_historic_monument_is_categorized_as_monument():
    assert "monument" in map_categories({"historic": "monument"})


def test_historic_memorial_is_not_automatically_a_monument():
    categories = map_categories({"historic": "memorial"})

    assert "monument" not in categories


def test_memorial_with_tourism_attraction_is_a_landmark():
    categories = map_categories({"historic": "memorial", "tourism": "attraction"})

    assert "landmark" in categories
    assert "monument" not in categories


def test_memorial_with_building_palace_keeps_palace_category():
    categories = map_categories({"historic": "memorial", "building": "palace"})

    assert "palace" in categories
    assert "monument" not in categories


def test_bar_tagged_as_attraction_stays_a_bar_first():
    categories = map_categories({"amenity": "bar", "tourism": "attraction"})

    assert categories == ["bar", "landmark"]


def test_cafe_in_a_historic_building_is_a_cafe_first():
    categories = map_categories({"amenity": "cafe", "historic": "building"})

    assert categories[0] == "cafe"


def test_park_tagged_as_attraction_is_a_park_first():
    categories = map_categories({"leisure": "park", "tourism": "attraction"})

    assert categories == ["park", "landmark"]


def test_attraction_alone_is_a_landmark():
    assert map_categories({"tourism": "attraction"}) == ["landmark"]


def test_christian_place_of_worship_without_building_tag_is_a_church():
    tags = {"amenity": "place_of_worship", "religion": "christian"}

    assert map_categories(tags) == ["church"]


def test_other_places_of_worship_are_not_churches():
    tags = {"amenity": "place_of_worship", "religion": "muslim"}

    assert "church" not in map_categories(tags)


def test_square_and_fountain_are_landmarks():
    assert map_categories({"place": "square"}) == ["landmark"]
    assert map_categories({"amenity": "fountain"}) == ["landmark"]


def test_neighbourhood_maps_to_neighborhood():
    assert map_categories({"place": "quarter"}) == ["neighborhood"]


def test_every_rule_output_has_defaults_and_only_day_trip_is_a_gap():
    vocab = load_vocabulary(CATEGORIES_FILE)

    check_against_vocabulary(vocab)
    assert unmapped_vocabulary(vocab) == ["day_trip"]
    assert "neighborhood" in mapped_categories()
