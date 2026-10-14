"""Tests for mapping OSM tags to controlled categories."""

from ingest.categories import map_categories


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
