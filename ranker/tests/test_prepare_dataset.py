"""Check combined dataset separation and saved-city preparation."""

import json

import pytest

from ranker.prepare_dataset import (
    build,
    check_place_separation,
    validate_city_lists,
)


def make_city(root, city, currency="EUR", count=30):
    folder = root / "data" / "out" / city
    folder.mkdir(parents=True)

    places = [
        {
            "id": f"osm:node/{city}-{number}",
            "name": f"Place {number}",
            "categories": ["museum"],
            "typical_duration_minutes": 60,
            "cost": {
                "amount": 10,
                "currency": currency,
                "confidence": "known",
            },
            "hours": {"confidence": "unknown"},
            "popularity": 0.5,
        }
        for number in range(count)
    ]

    (folder / "places.json").write_text(
        json.dumps(places), encoding="utf-8"
    )
    (folder / "city.json").write_text(
        json.dumps({
            "name": city,
            "currency": currency,
        }),
        encoding="utf-8",
    )
    return folder


@pytest.fixture
def cities(tmp_path):
    make_city(tmp_path, "training")
    make_city(tmp_path, "testing", "JPY")
    return tmp_path


def budgets():
    return {
        "EUR": [300, 600],
        "JPY": [30000, 60000],
    }


def place_ids(queries):
    return {
        item["place"]["id"]
        for query in queries
        for item in query["items"]
    }


def test_city_cannot_appear_in_both_groups():
    with pytest.raises(ValueError, match="both sets"):
        validate_city_lists(["rome"], ["rome"])


def test_duplicate_training_city_is_rejected():
    with pytest.raises(ValueError, match="Duplicate training"):
        validate_city_lists(["rome", "rome"], ["tokyo"])


def test_duplicate_testing_city_is_rejected():
    with pytest.raises(ValueError, match="Duplicate testing"):
        validate_city_lists(["rome"], ["tokyo", "tokyo"])


def test_shared_place_ids_are_rejected():
    with pytest.raises(ValueError, match="place IDs"):
        check_place_separation({"osm:1"}, {"osm:1"})


def test_build_separates_cities_and_profiles(cities):
    datasets, summary = build(
        cities,
        budgets(),
        ["training"],
        ["testing"],
        travelers=100,
        place_limit=20,
    )

    assert len(datasets["test"]) == 100
    assert (
        len(datasets["train"]) + len(datasets["validation"])
    ) == 100

    development = datasets["train"] + datasets["validation"]
    assert all(
        place_id.startswith("osm:node/training-")
        for place_id in place_ids(development)
    )
    assert all(
        place_id.startswith("osm:node/testing-")
        for place_id in place_ids(datasets["test"])
    )

    train_profiles = {
        json.dumps(q["profile"], sort_keys=True)
        for q in datasets["train"]
    }
    validation_profiles = {
        json.dumps(q["profile"], sort_keys=True)
        for q in datasets["validation"]
    }
    assert not train_profiles & validation_profiles
    assert summary["test_only_cities"] == ["testing"]


def test_place_sampling_respects_limit(cities):
    _, summary = build(
        cities,
        budgets(),
        ["training"],
        ["testing"],
        travelers=100,
        place_limit=20,
    )

    assert all(
        source["sampled_places"] == 20
        for source in summary["sources"]
    )


def test_build_is_repeatable(cities):
    arguments = (
        cities, budgets(), ["training"], ["testing"]
    )

    first = build(*arguments, travelers=100, place_limit=20)
    second = build(*arguments, travelers=100, place_limit=20)

    assert first == second


def test_missing_city_is_rejected(cities):
    with pytest.raises(FileNotFoundError, match="missing"):
        build(
            cities,
            budgets(),
            ["missing"],
            ["testing"],
            travelers=100,
        )


def test_empty_city_is_rejected(cities):
    path = cities / "data/out/training/places.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="15 places"):
        build(
            cities,
            budgets(),
            ["training"],
            ["testing"],
            travelers=100,
        )


def test_mixed_currency_is_rejected(cities):
    path = cities / "data/out/training/places.json"
    places = json.loads(path.read_text(encoding="utf-8"))
    places[0]["cost"]["currency"] = "USD"
    path.write_text(json.dumps(places), encoding="utf-8")

    with pytest.raises(ValueError, match="currencies"):
        build(
            cities,
            budgets(),
            ["training"],
            ["testing"],
            travelers=100,
        )


def test_invalid_budget_is_rejected(cities):
    options = budgets()
    options["EUR"] = [-1]

    with pytest.raises(ValueError, match="budget"):
        build(
            cities,
            options,
            ["training"],
            ["testing"],
            travelers=100,
        )


def test_source_overlap_is_checked_before_sampling(cities):
    training_path = cities / "data/out/training/places.json"
    testing_path = cities / "data/out/testing/places.json"

    training = json.loads(
        training_path.read_text(encoding="utf-8")
    )
    testing = json.loads(
        testing_path.read_text(encoding="utf-8")
    )
    testing[-1]["id"] = training[-1]["id"]
    testing_path.write_text(
        json.dumps(testing), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="place IDs"):
        build(
            cities,
            budgets(),
            ["training"],
            ["testing"],
            travelers=100,
            place_limit=15,
        )