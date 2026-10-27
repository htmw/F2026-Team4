"""Tests for automatic compact ranking-data preparation."""

import argparse
import json
import sys

import pytest

from ranker import prepare_live
from ranker.dataset_io import load_dataset
from ranker.features import feature_names


def make_places(currency="USD"):
    return [
        {
            "id": f"osm:node/{number}",
            "name": f"Test Place {number}",
            "lat": 40.7,
            "lon": -74.0,
            "categories": ["museum"],
            "typical_duration_minutes": 60,
            "cost": {
                "amount": 10.0,
                "currency": currency,
                "confidence": "known",
            },
            "hours": {"confidence": "unknown"},
            "popularity": 0.5,
        }
        for number in range(20)
    ]


@pytest.mark.parametrize(
    "name",
    ["Tokyo, Japan", "Bogotá, Colombia", "Hyderabad, India"],
)
def test_reserved_cities_are_testing_only(name):
    assert prepare_live.is_test_city("example", name, {})


def test_destination_metadata_identifies_reserved_city():
    assert prepare_live.is_test_city(
        "example",
        "Example destination",
        {"name": "Tokyo, Japan"},
    )


def test_normal_city_is_not_reserved():
    assert not prepare_live.is_test_city(
        "rome", "Rome, Italy", {"name": "Rome"}
    )


def test_local_currency_and_supplied_budgets_are_used():
    queries = prepare_live.build_queries(
        make_places("INR"),
        "INR",
        [5000.0, 10000.0],
        travelers=10,
        candidates=5,
        seed=42,
    )

    for query in queries:
        assert query["profile"]["budget"]["currency"] == "INR"
        assert query["profile"]["budget"]["total"] in {
            5000.0, 10000.0
        }
        for item in query["items"]:
            assert len(item["features"]) == len(feature_names())
            assert 0 <= item["relevance"] <= 4


def test_mixed_currencies_are_rejected():
    places = make_places()
    places[0]["cost"]["currency"] = "EUR"

    with pytest.raises(ValueError, match="Mixed currencies"):
        prepare_live.build_queries(
            places, "USD", [500.0], 10, 5, 42
        )


def test_duplicate_place_ids_are_rejected():
    places = make_places()
    places[1]["id"] = places[0]["id"]

    with pytest.raises(ValueError, match="Duplicate"):
        prepare_live.build_queries(
            places, "USD", [500.0], 10, 5, 42
        )


def test_invalid_cost_is_rejected():
    places = make_places()
    places[0]["cost"]["amount"] = float("nan")

    with pytest.raises(ValueError, match="Invalid cost"):
        prepare_live.build_queries(
            places, "USD", [500.0], 10, 5, 42
        )


def test_bbox_is_parsed():
    assert prepare_live.parse_bbox(
        "35.60,139.60,35.82,139.92"
    ) == (35.60, 139.60, 35.82, 139.92)


def test_invalid_bbox_is_rejected():
    with pytest.raises(argparse.ArgumentTypeError):
        prepare_live.parse_bbox("50,10,40,20")


def test_saved_city_is_reused_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare_live, "ROOT", tmp_path)

    folder = tmp_path / "data/out/example"
    folder.mkdir(parents=True)
    places = make_places()
    metadata = {"name": "Example", "currency": "USD"}

    (folder / "places.json").write_text(
        json.dumps(places), encoding="utf-8"
    )
    (folder / "city.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )

    def unexpected_fetch(*args, **kwargs):
        pytest.fail("Saved city should not trigger ingestion.")

    monkeypatch.setattr(prepare_live, "run_city", unexpected_fetch)

    loaded, info, source = prepare_live.load_city(
        "Example", "example", False, None
    )

    assert loaded == places
    assert info == metadata
    assert source == folder


def test_missing_city_calls_ingest(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare_live, "ROOT", tmp_path)
    calls = []

    def fake_ingest(query, **kwargs):
        calls.append((query, kwargs))
        folder = kwargs["out_dir"] / kwargs["slug"]
        folder.mkdir(parents=True)
        (folder / "city.json").write_text(
            json.dumps({"name": "Example", "currency": "USD"}),
            encoding="utf-8",
        )
        return {
            "places": make_places(),
            "out_dir": folder,
        }

    monkeypatch.setattr(prepare_live, "run_city", fake_ingest)

    places, metadata, _ = prepare_live.load_city(
        "Example", "example", False, None
    )

    assert len(calls) == 1
    assert calls[0][1]["matrix_top"] == 0
    assert len(places) == 20
    assert metadata["currency"] == "USD"


def run_preparation(tmp_path, monkeypatch, city, slug, currency):
    monkeypatch.setattr(prepare_live, "ROOT", tmp_path)

    def saved_city(*args, **kwargs):
        return (
            make_places(currency),
            {"name": city, "currency": currency},
            tmp_path / "source",
        )

    monkeypatch.setattr(prepare_live, "load_city", saved_city)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare_live",
            city,
            "--slug", slug,
            "--budgets", "500", "1000",
            "--travelers", "200",
            "--candidates", "5",
        ],
    )

    prepare_live.main()
    return tmp_path / "data/ranking_compact" / slug


def test_reserved_city_creates_only_testing_data(tmp_path, monkeypatch):
    output = run_preparation(
        tmp_path, monkeypatch, "Tokyo, Japan", "tokyo", "JPY"
    )

    assert not (output / "train.json").exists()
    assert len(load_dataset(output / "test.json")) == 200

    summary = json.loads(
        (output / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["test_only_city"] is True
    assert summary["train_queries"] == 0


def test_normal_city_creates_separate_sets(tmp_path, monkeypatch):
    output = run_preparation(
        tmp_path, monkeypatch, "Example, USA", "example", "USD"
    )

    train = load_dataset(output / "train.json")
    test = load_dataset(output / "test.json")

    assert train
    assert test
    assert len(train) + len(test) == 200

    train_profiles = {
        json.dumps(query["profile"], sort_keys=True)
        for query in train
    }
    test_profiles = {
        json.dumps(query["profile"], sort_keys=True)
        for query in test
    }
    assert not train_profiles & test_profiles


def test_existing_train_file_blocks_reserved_city(tmp_path, monkeypatch):
    folder = tmp_path / "data/ranking_compact/tokyo"
    folder.mkdir(parents=True)
    train_file = folder / "train.json"
    train_file.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="reserved test city"):
        run_preparation(
            tmp_path, monkeypatch, "Tokyo, Japan", "tokyo", "JPY"
        )

    assert train_file.read_text(encoding="utf-8") == "[]"