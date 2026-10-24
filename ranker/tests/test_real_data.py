"""Tests for preparing ranking data from real places."""

import json
import math
from pathlib import Path

import pytest

from ranker.features import feature_names
from ranker.real_data import make_dataset, save_json, split_dataset
from ranker.synthetic import to_matrix

ROOT = Path(__file__).resolve().parents[2]
PLACES = ROOT / "data" / "cities" / "rome" / "places.json"


@pytest.fixture(scope="module")
def queries():
    return make_dataset(PLACES, n_travelers=20, k=15, seed=42)


def test_examples_keep_the_existing_model_format(queries):
    for query in queries:
        assert set(query) == {"profile", "items"}
        assert len(query["items"]) == 15

        for item in query["items"]:
            assert set(item) == {"place", "relevance", "features"}
            assert isinstance(item["relevance"], int)
            assert 0 <= item["relevance"] <= 4
            assert len(item["features"]) == len(feature_names())
            assert all(math.isfinite(value) for value in item["features"])


def test_candidates_come_from_the_source_without_changes(queries):
    places = json.loads(PLACES.read_text(encoding="utf-8"))
    source = {place["id"]: place for place in places}

    for query in queries:
        ids = [item["place"]["id"] for item in query["items"]]
        assert len(ids) == len(set(ids))

        for item in query["items"]:
            place = item["place"]
            assert place == source[place["id"]]
            assert not place["id"].startswith("syn:")


def test_same_seed_reproduces_the_examples(queries):
    repeated = make_dataset(PLACES, n_travelers=20, k=15, seed=42)
    assert repeated == queries


def test_split_keeps_travelers_separate_and_preserves_examples(queries):
    train, test = split_dataset(queries)

    assert len(train) == 16
    assert len(test) == 4

    def key(query):
        return json.dumps(query["profile"], sort_keys=True)

    assert not ({key(q) for q in train} & {key(q) for q in test})
    assert sorted(map(key, train + test)) == sorted(map(key, queries))

    repeated_train, repeated_test = split_dataset(queries)
    assert train == repeated_train
    assert test == repeated_test


def test_examples_work_with_the_existing_matrix_converter(queries):
    x, y, groups = to_matrix(queries)

    assert x.shape == (300, len(feature_names()))
    assert y.shape == (300,)
    assert groups == [15] * 20
    assert sum(groups) == len(y)


def test_missing_ratings_are_not_invented(tmp_path):
    places = json.loads(PLACES.read_text(encoding="utf-8"))[:15]
    for place in places:
        place.pop("rating", None)

    source = tmp_path / "places.json"
    save_json(source, places)
    examples = make_dataset(source, n_travelers=2)
    rating_index = feature_names().index("rating_norm")

    for query in examples:
        for item in query["items"]:
            assert "rating" not in item["place"]
            assert item["features"][rating_index] == 0.0


def test_duplicate_source_ids_are_rejected(tmp_path):
    places = json.loads(PLACES.read_text(encoding="utf-8"))[:15]
    places[-1] = places[0]
    source = tmp_path / "duplicates.json"
    save_json(source, places)

    with pytest.raises(ValueError, match="duplicate"):
        make_dataset(source)


def test_too_few_places_are_rejected(tmp_path):
    source = tmp_path / "empty.json"
    save_json(source, [])

    with pytest.raises(ValueError, match="at least"):
        make_dataset(source)


def test_synthetic_places_are_rejected(tmp_path):
    places = json.loads(PLACES.read_text(encoding="utf-8"))[:15]
    places[0]["id"] = "syn:0"
    source = tmp_path / "synthetic.json"
    save_json(source, places)

    with pytest.raises(ValueError, match="Synthetic"):
        make_dataset(source)


def test_saved_examples_can_be_loaded_again(tmp_path, queries):
    output = tmp_path / "examples.json"
    save_json(output, queries)

    assert json.loads(output.read_text(encoding="utf-8")) == queries