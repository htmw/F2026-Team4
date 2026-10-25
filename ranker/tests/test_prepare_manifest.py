"""Check manifest snapshots, offline reuse and city separation."""

import copy
import json

import pytest

from ingest import catalog
from ranker.prepare_manifest import (
    check_source_ids,
    ensure_snapshot,
    validate_manifest,
)


def city_spec(key="example-us", role="train"):
    return {
        "key": key,
        "query": "Example, USA",
        "country": "US",
        "currency": "USD",
        "region": "North America",
        "role": role,
    }


def manifest():
    return {
        "version": 1,
        "seed": 42,
        "travelers_per_city": 100,
        "maximum_places_per_city": 20,
        "candidates_per_traveler": 15,
        "budgets": {"USD": [300, 600]},
        "cities": [
            city_spec("training-us", "train"),
            city_spec("testing-us", "test"),
        ],
    }


def source_city(tmp_path, country="US", currency="USD"):
    folder = tmp_path / "live" / "example-us"
    folder.mkdir(parents=True)

    places = [
        {
            "id": f"osm:node/{number}",
            "name": f"Place {number}",
            "lat": 40.7,
            "lon": -74.0,
            "categories": ["museum"],
            "typical_duration_minutes": 60,
            "cost": {
                "amount": 10,
                "currency": currency,
                "confidence": "known",
            },
            "hours": {"confidence": "unknown"},
            "popularity": 0.5,
            "rating": 4.5,
        }
        for number in range(30)
    ]

    (folder / "places.json").write_text(
        json.dumps(places), encoding="utf-8"
    )
    (folder / "city.json").write_text(
        json.dumps({
            "name": "Example, USA",
            "country": country,
            "currency": currency,
            "attribution": "OpenStreetMap contributors",
        }),
        encoding="utf-8",
    )
    return folder


def test_valid_manifest_is_accepted():
    validate_manifest(manifest())


def test_duplicate_city_key_is_rejected():
    data = manifest()
    data["cities"][1]["key"] = data["cities"][0]["key"]

    with pytest.raises(ValueError, match="unique"):
        validate_manifest(data)


def test_unsafe_city_key_is_rejected():
    data = manifest()
    data["cities"][0]["key"] = "../outside"

    with pytest.raises(ValueError, match="Invalid city key"):
        validate_manifest(data)


def test_invalid_budget_is_rejected():
    data = manifest()
    data["budgets"]["USD"] = [-1]

    with pytest.raises(ValueError, match="budget"):
        validate_manifest(data)


def test_missing_budget_configuration_is_rejected():
    data = manifest()
    data["budgets"] = {}

    with pytest.raises(ValueError, match="budget"):
        validate_manifest(data)


def test_missing_offline_snapshot_does_not_fetch(
    tmp_path, monkeypatch
):
    def unexpected_fetch(name):
        pytest.fail("Offline preparation must not fetch.")

    monkeypatch.setattr(catalog, "fetch_live", unexpected_fetch)

    with pytest.raises(FileNotFoundError, match="snapshot"):
        ensure_snapshot(
            tmp_path / "snapshots",
            city_spec(),
            20,
            42,
            offline=True,
        )


def test_missing_snapshot_fetches_and_saves_compact_source(
    tmp_path, monkeypatch
):
    source = source_city(tmp_path)
    calls = []

    def fake_fetch(name):
        calls.append(name)
        return source

    monkeypatch.setattr(catalog, "fetch_live", fake_fetch)
    snapshots = tmp_path / "snapshots"

    lock = ensure_snapshot(
        snapshots, city_spec(), 20, 42, offline=False
    )

    folder = snapshots / "data/out/example-us"
    selected = json.loads(
        (folder / "places.json").read_text(encoding="utf-8")
    )
    all_ids = json.loads(
        (folder / "source_ids.json").read_text(encoding="utf-8")
    )

    assert calls == ["Example, USA"]
    assert lock["source_places"] == 30
    assert len(selected) == 20
    assert len(all_ids) == 30
    assert "lat" not in selected[0]
    assert selected[0]["rating"] == 4.5
    assert (folder / "snapshot.json").is_file()


def test_existing_snapshot_can_be_reused_offline(
    tmp_path, monkeypatch
):
    source = source_city(tmp_path)
    monkeypatch.setattr(
        catalog, "fetch_live", lambda name: source
    )
    snapshots = tmp_path / "snapshots"

    original = ensure_snapshot(
        snapshots, city_spec(), 20, 42, offline=False
    )

    def unexpected_fetch(name):
        pytest.fail("Saved snapshots must not require a fetch.")

    monkeypatch.setattr(catalog, "fetch_live", unexpected_fetch)

    reused = ensure_snapshot(
        snapshots, city_spec(), 20, 42, offline=True
    )

    assert reused == original


def test_modified_snapshot_fails_checksum(
    tmp_path, monkeypatch
):
    source = source_city(tmp_path)
    monkeypatch.setattr(
        catalog, "fetch_live", lambda name: source
    )
    snapshots = tmp_path / "snapshots"
    ensure_snapshot(
        snapshots, city_spec(), 20, 42, offline=False
    )

    path = snapshots / "data/out/example-us/places.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="checksum"):
        ensure_snapshot(
            snapshots, city_spec(), 20, 42, offline=True
        )


def test_changed_snapshot_settings_are_rejected(
    tmp_path, monkeypatch
):
    source = source_city(tmp_path)
    monkeypatch.setattr(
        catalog, "fetch_live", lambda name: source
    )
    snapshots = tmp_path / "snapshots"
    ensure_snapshot(
        snapshots, city_spec(), 20, 42, offline=False
    )

    with pytest.raises(ValueError, match="configuration differs"):
        ensure_snapshot(
            snapshots, city_spec(), 25, 42, offline=True
        )


def test_wrong_country_is_rejected(tmp_path, monkeypatch):
    source = source_city(tmp_path, country="CA")
    monkeypatch.setattr(
        catalog, "fetch_live", lambda name: source
    )

    with pytest.raises(ValueError, match="country"):
        ensure_snapshot(
            tmp_path / "snapshots",
            city_spec(),
            20,
            42,
            offline=False,
        )


def test_wrong_currency_is_rejected(tmp_path, monkeypatch):
    source = source_city(tmp_path, currency="EUR")
    monkeypatch.setattr(
        catalog, "fetch_live", lambda name: source
    )

    with pytest.raises(ValueError, match="currency"):
        ensure_snapshot(
            tmp_path / "snapshots",
            city_spec(),
            20,
            42,
            offline=False,
        )


def test_full_source_overlap_is_rejected(tmp_path):
    specs = [
        city_spec("training-us", "train"),
        city_spec("testing-us", "test"),
    ]

    for spec in specs:
        folder = tmp_path / "data/out" / spec["key"]
        folder.mkdir(parents=True)
        (folder / "source_ids.json").write_text(
            json.dumps(["osm:node/shared"]),
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match="place IDs"):
        check_source_ids(tmp_path, specs)


def test_disjoint_full_source_ids_are_accepted(tmp_path):
    specs = [
        city_spec("training-us", "train"),
        city_spec("testing-us", "test"),
    ]

    for number, spec in enumerate(specs):
        folder = tmp_path / "data/out" / spec["key"]
        folder.mkdir(parents=True)
        (folder / "source_ids.json").write_text(
            json.dumps([f"osm:node/{number}"]),
            encoding="utf-8",
        )

    check_source_ids(tmp_path, specs)