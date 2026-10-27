"""Verify compact storage preserves the current model inputs."""

import copy
import json

import numpy as np
import pytest

from ranker.dataset_io import (
    FORMAT,
    LEGACY_FORMAT,
    load_dataset,
    save_dataset,
)
from ranker.features import extract_features
from ranker.synthetic import to_matrix


def example_queries():
    museum = {
        "id": "osm:node/1",
        "name": "Example Museum",
        "lat": 40.7,
        "lon": -74.0,
        "categories": ["museum"],
        "typical_duration_minutes": 90,
        "cost": {
            "amount": 15,
            "currency": "USD",
            "confidence": "known",
        },
        "hours": {
            "mon": [["09:00", "17:00"]],
            "confidence": "known",
        },
        "rating": 4.5,
        "popularity": 0.7,
        "source": "osm",
    }

    park = {
        "id": "osm:node/2",
        "name": "Example Park",
        "categories": ["park"],
        "typical_duration_minutes": 60,
        "cost": {
            "amount": 0,
            "currency": "USD",
            "confidence": "unknown",
        },
        "hours": {"confidence": "unknown"},
        "popularity": 0.4,
    }

    queries = []

    for interests in (
        {"history": 1.0, "nature": 0.2},
        {"history": 0.2, "nature": 1.0},
    ):
        profile = {
            "interests": interests,
            "budget": {"total": 600, "currency": "USD"},
            "novelty_appetite": 0.3,
        }
        queries.append({
            "profile": profile,
            "items": [
                {
                    "place": copy.deepcopy(place),
                    "relevance": grade,
                    "features": extract_features(place, profile),
                }
                for place, grade in ((museum, 4), (park, 1))
            ],
        })

    return queries


def test_model_matrix_is_preserved(tmp_path):
    queries = example_queries()
    path = tmp_path / "dataset.json"

    save_dataset(path, queries)
    restored = load_dataset(path)

    before_x, before_y, before_groups = to_matrix(queries)
    after_x, after_y, after_groups = to_matrix(restored)

    np.testing.assert_array_equal(before_x, after_x)
    np.testing.assert_array_equal(before_y, after_y)
    assert before_groups == after_groups

    assert [q["profile"] for q in restored] == [
        q["profile"] for q in queries
    ]


def test_places_are_stored_once_and_features_are_not_repeated(tmp_path):
    path = tmp_path / "dataset.json"
    save_dataset(path, example_queries())

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["format"] == FORMAT
    assert len(payload["places"]) == 2

    for query in payload["queries"]:
        for item in query["items"]:
            assert set(item) == {"place_id", "relevance"}


def test_unused_details_are_removed(tmp_path):
    path = tmp_path / "dataset.json"
    save_dataset(path, example_queries())

    payload = json.loads(path.read_text(encoding="utf-8"))
    museum = payload["places"]["osm:node/1"]

    assert "lat" not in museum
    assert "lon" not in museum
    assert "source" not in museum
    assert museum["hours"] == {"confidence": "known"}


def test_existing_rating_and_popularity_are_preserved(tmp_path):
    path = tmp_path / "dataset.json"
    save_dataset(path, example_queries())

    museum = load_dataset(path)[0]["items"][0]["place"]

    assert museum["rating"] == 4.5
    assert museum["popularity"] == 0.7


def test_missing_rating_is_not_invented(tmp_path):
    path = tmp_path / "dataset.json"
    save_dataset(path, example_queries())

    park = load_dataset(path)[0]["items"][1]["place"]

    assert "rating" not in park


def test_conflicting_model_details_are_rejected(tmp_path):
    queries = example_queries()
    item = queries[1]["items"][0]
    item["place"]["popularity"] = 0.2
    item["features"] = extract_features(
        item["place"], queries[1]["profile"]
    )

    with pytest.raises(ValueError, match="Conflicting"):
        save_dataset(tmp_path / "dataset.json", queries)


def test_incorrect_stored_features_are_rejected(tmp_path):
    queries = example_queries()
    queries[0]["items"][0]["features"][0] += 1

    with pytest.raises(ValueError, match="Stored features"):
        save_dataset(tmp_path / "dataset.json", queries)


def test_missing_place_reference_is_rejected(tmp_path):
    path = tmp_path / "dataset.json"
    save_dataset(path, example_queries())

    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["places"]["osm:node/1"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="missing place"):
        load_dataset(path)


def test_expanded_legacy_files_still_load(tmp_path):
    queries = example_queries()
    path = tmp_path / "old.json"
    path.write_text(json.dumps(queries), encoding="utf-8")

    assert load_dataset(path) == queries


def test_v1_compact_files_still_load(tmp_path):
    queries = example_queries()
    places = {}
    stored_queries = []

    for query in queries:
        items = []
        for item in query["items"]:
            place = item["place"]
            places[place["id"]] = place
            items.append({
                "place_id": place["id"],
                "relevance": item["relevance"],
                "features": item["features"],
            })
        stored_queries.append({
            "profile": query["profile"],
            "items": items,
        })

    path = tmp_path / "v1.json"
    path.write_text(
        json.dumps({
            "format": LEGACY_FORMAT,
            "places": places,
            "queries": stored_queries,
        }),
        encoding="utf-8",
    )

    assert load_dataset(path) == queries


def test_changed_feature_names_are_rejected(tmp_path):
    path = tmp_path / "dataset.json"
    save_dataset(path, example_queries())

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["feature_names"] = ["different_feature"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="feature names"):
        load_dataset(path)


def test_unsupported_format_is_rejected(tmp_path):
    path = tmp_path / "dataset.json"
    path.write_text(
        json.dumps({"format": "unsupported"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported"):
        load_dataset(path)


def test_invalid_grade_is_rejected(tmp_path):
    queries = example_queries()
    queries[0]["items"][0]["relevance"] = 5

    with pytest.raises(ValueError, match="Relevance"):
        save_dataset(tmp_path / "dataset.json", queries)


def test_nonfinite_data_does_not_create_output(tmp_path):
    queries = example_queries()
    queries[0]["profile"]["extra"] = float("nan")
    path = tmp_path / "dataset.json"

    with pytest.raises(ValueError):
        save_dataset(path, queries)

    assert not path.exists()


def test_tiny_saved_feature_rounding_is_accepted(tmp_path):
    queries = example_queries()
    queries[0]["items"][0]["features"][0] += 1e-14
    path = tmp_path / "dataset.json"

    save_dataset(path, queries)

    before_x, before_y, before_groups = to_matrix(queries)
    after_x, after_y, after_groups = to_matrix(load_dataset(path))

    np.testing.assert_allclose(
        before_x,
        after_x,
        rtol=1e-12,
        atol=1e-12,
    )
    np.testing.assert_array_equal(before_y, after_y)
    assert before_groups == after_groups