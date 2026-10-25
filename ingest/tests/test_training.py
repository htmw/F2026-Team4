"""The frozen training file: small, repeatable, split by city, and in the ranker's shape."""

from __future__ import annotations

import json

import pytest

from ingest.cache import write_json
from ingest.training import build, load_queries
from ranker.features import FEATURE_NAMES


def _place(city: str, i: int, currency: str = "EUR") -> dict:
    return {
        "id": f"osm:node/{city}{i}",
        "name": f"Place {i}",
        "lat": 1.0,
        "lon": 2.0,
        "categories": ["museum" if i % 2 else "cafe"],
        "typical_duration_minutes": 45,
        "cost": {"amount": 0.0, "currency": currency, "confidence": "inferred"},
        "hours": {"mon": None, "confidence": "known"},
        "popularity": i / 40,
        "source": "osm",
    }


@pytest.fixture
def live(tmp_path):
    for city, n, currency in [("big", 40, "EUR"), ("small", 6, "EUR"), ("unseen", 20, "JPY")]:
        (tmp_path / city).mkdir()
        places = [_place(city, i, currency) for i in range(n)]
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


def test_travelers_have_budgets_in_the_city_currency(live):
    data = build(live, ["big"], ["unseen"], per_city=10, travelers=5)
    euro = {q["profile"]["budget"]["currency"] for q in data["train"]}
    yen = [q["profile"]["budget"] for q in data["test"]]

    assert euro == {"EUR"}
    assert {b["currency"] for b in yen} == {"JPY"}
    assert min(b["total"] for b in yen) >= 300 * 165


def test_a_currency_without_a_budget_factor_stops_the_build(live):
    (live / "big" / "places.json").write_text(
        json.dumps([_place("big", i, "XXX") for i in range(5)]), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="XXX"):
        build(live, ["big"], [])


def test_a_validation_set_comes_from_the_training_cities(live):
    data = build(live, ["big"], ["unseen"], per_city=10, travelers=10)

    assert len(data["train"]) == 8 and len(data["validation"]) == 2
    assert {q["city"] for q in data["validation"]} == {"big"}
    assert len(load_queries_from(data, live, "validation")) == 2


def test_a_place_in_training_never_shows_up_in_a_test_city(live):
    shared = _place("big", 1)
    places = json.loads((live / "unseen" / "places.json").read_text(encoding="utf-8"))
    (live / "unseen" / "places.json").write_text(json.dumps(places + [shared]), encoding="utf-8")
    data = build(live, ["big"], ["unseen"], per_city=100, travelers=2)

    train_ids = {p["id"] for p in data["cities"]["big"]}
    test_ids = {p["id"] for p in data["cities"]["unseen"]}
    assert shared["id"] in train_ids
    assert not train_ids & test_ids


def load_queries_from(data, folder, split):
    path = folder / "dataset.json"
    write_json(path, data)
    return load_queries(split, path)
