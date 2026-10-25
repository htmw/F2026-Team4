"""The frozen training file: small, repeatable, split by city, and in the ranker's shape."""

from __future__ import annotations

import json

import pytest

from ingest.cache import write_json
from ingest.training import build, load_queries
from ranker.features import FEATURE_NAMES


def _place(city: str, i: int) -> dict:
    return {
        "id": f"osm:node/{city}{i}",
        "name": f"Place {i}",
        "lat": 1.0,
        "lon": 2.0,
        "categories": ["museum" if i % 2 else "cafe"],
        "typical_duration_minutes": 45,
        "cost": {"amount": 0.0, "currency": "EUR", "confidence": "inferred"},
        "hours": {"mon": None, "confidence": "known"},
        "popularity": i / 40,
        "source": "osm",
    }


@pytest.fixture
def live(tmp_path):
    for city, n in [("big", 40), ("small", 6), ("unseen", 20)]:
        (tmp_path / city).mkdir()
        places = [_place(city, i) for i in range(n)]
        (tmp_path / city / "places.json").write_text(json.dumps(places), encoding="utf-8")
    return tmp_path


def test_test_cities_are_never_trained_on(live):
    data = build(live, ["big", "small"], ["unseen"], per_city=10, travelers=5)

    assert {q["city"] for q in data["train"]} == {"big", "small"}
    assert {q["city"] for q in data["test"]} == {"unseen"}
    assert len(data["cities"]["big"]) == 10
    assert len(data["cities"]["small"]) == 6, "a small city keeps all its places"


def test_places_are_stored_once_with_only_what_the_ranker_reads(live):
    data = build(live, ["big"], [], per_city=10, travelers=5)
    place = data["cities"]["big"][0]

    assert "lat" not in place and "source" not in place
    assert place["hours"] == {"confidence": "known"}
    assert set(data["train"][0]["items"][0]) == {"place_id", "relevance"}


def test_the_same_input_gives_the_same_file(live):
    assert build(live, ["big"], ["unseen"], travelers=5) == build(
        live, ["big"], ["unseen"], travelers=5
    )


def test_load_queries_gives_the_ranker_its_usual_shape(live, tmp_path):
    path = tmp_path / "dataset.json"
    write_json(path, build(live, ["big"], ["unseen"], per_city=10, travelers=3))
    queries = load_queries("test", path)

    assert len(queries) == 3
    item = queries[0]["items"][0]
    assert set(item) == {"place", "relevance", "features"}
    assert len(item["features"]) == len(FEATURE_NAMES)
    assert 0 <= item["relevance"] <= 4


def test_a_city_not_fetched_yet_is_named(live):
    with pytest.raises(FileNotFoundError, match="porto-pt"):
        build(live, ["big", "porto-pt"], [])
