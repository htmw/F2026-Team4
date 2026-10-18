"""Tests for applying hand checked facts on top of OSM records."""

import json
from pathlib import Path

import pytest

from ingest.curation import CurationError, apply_curation, find_match, load_curation
from ingest.to_place import make_validator

SCHEMA = Path(__file__).resolve().parents[2] / "contracts" / "place.schema.json"


def _place(pid, name, lat, lon, pop=0.5):
    hours = {d: [["00:00", "23:59"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
    hours["confidence"] = "inferred"
    return {
        "id": pid,
        "name": name,
        "lat": lat,
        "lon": lon,
        "categories": ["landmark"],
        "typical_duration_minutes": 30,
        "cost": {"amount": 0.0, "currency": "EUR", "confidence": "inferred"},
        "hours": hours,
        "source": "osm",
        "last_verified": "2026-10-17",
        "popularity": pop,
    }


@pytest.fixture
def places():
    return [
        _place("osm:way/1", "Colosseo", 41.8902, 12.4922, pop=1.0),
        _place("osm:node/2", "Pantheon", 41.8986, 12.4769, pop=0.9),
        _place("osm:node/3", "Colosseo", 41.95, 12.40, pop=0.1),  # a bar far away
    ]


@pytest.fixture
def signals():
    return {
        "osm:way/1": {"names": ["anfiteatro flavio", "colosseo", "colosseum"]},
        "osm:node/2": {"names": ["pantheon"]},
        "osm:node/3": {"names": ["colosseo"]},
    }


def _entry(**overrides):
    entry = {
        "name": "Colosseum",
        "match": {"names": ["Colosseo"], "near": [41.8902, 12.4922], "radius_m": 300},
        "opening_hours": "Mo-Su 08:30-16:30",
        "price": {"amount": 18.0, "currency": "EUR"},
        "duration_minutes": 120,
        "sources": ["https://colosseo.it/en/"],
    }
    entry.update(overrides)
    return entry


def _write(tmp_path, data):
    path = tmp_path / "rome.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_curated_facts_become_known_and_stay_valid(places, signals):
    curation = {"checked_on": "2026-10-17", "places": [_entry()]}
    out, report = apply_curation(places, curation, signals, make_validator(SCHEMA))
    colosseum = next(p for p in out if p["id"] == "osm:way/1")

    assert report.unmatched == []
    assert colosseum["hours"]["confidence"] == "known"
    assert colosseum["hours"]["mon"] == [["08:30", "16:30"]]
    assert colosseum["cost"] == {"amount": 18.0, "currency": "EUR", "confidence": "known"}
    assert colosseum["typical_duration_minutes"] == 120
    assert colosseum["source"] == "osm+curated"
    assert colosseum["last_verified"] == "2026-10-17"
    # The input list is left alone.
    assert places[0]["hours"]["confidence"] == "inferred"


def test_match_uses_other_language_names_and_distance(places, signals):
    entry = _entry(match={"names": ["Anfiteatro Flavio"], "near": [41.8902, 12.4922]})

    assert find_match(entry, places, signals)["id"] == "osm:way/1"


def test_entry_too_far_from_any_match_is_reported(places, signals):
    entry = _entry(match={"names": ["Colosseo"], "near": [41.80, 12.30], "radius_m": 200})
    _, report = apply_curation(places, {"checked_on": "2026-10-17", "places": [entry]}, signals)

    assert report.unmatched == ["Colosseum"]


def test_pinned_id_wins_over_names(places, signals):
    entry = _entry(match={"id": "osm:node/2"})

    assert find_match(entry, places, signals)["id"] == "osm:node/2"


def test_excluded_ids_are_dropped(places, signals):
    curation = {
        "checked_on": "2026-10-17",
        "places": [],
        "exclude": [{"id": "osm:node/3", "reason": "a bar, not the sight"}],
    }
    out, report = apply_curation(places, curation, signals)

    assert [p["id"] for p in out] == ["osm:way/1", "osm:node/2"]
    assert report.excluded == ["osm:node/3"]


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"opening_hours": "Mo-Su 08:30-16:30 (last entry 15:30)"}, "cannot be parsed"),
        ({"price": {"amount": 18, "currency": "EURO"}}, "ISO 4217"),
        ({"price": {"amount": -1, "currency": "EUR"}}, ">= 0"),
        ({"duration_minutes": 2}, "duration_minutes"),
        ({"sources": []}, "source URL"),
    ],
)
def test_load_curation_rejects_bad_entries(tmp_path, overrides, message):
    path = _write(tmp_path, {"checked_on": "2026-10-17", "places": [_entry(**overrides)]})

    with pytest.raises(CurationError, match=message):
        load_curation(path)


def test_load_curation_requires_a_check_date(tmp_path):
    path = _write(tmp_path, {"places": []})

    with pytest.raises(CurationError, match="checked_on"):
        load_curation(path)


def test_load_curation_accepts_a_good_file(tmp_path):
    path = _write(tmp_path, {"checked_on": "2026-10-17", "places": [_entry()]})

    assert load_curation(path)["places"][0]["name"] == "Colosseum"


def test_point_in_polygon_square():
    from ingest.curation import point_in_polygon

    square = [[0, 0], [0, 1], [1, 1], [1, 0]]

    assert point_in_polygon(0.5, 0.5, square)
    assert not point_in_polygon(1.5, 0.5, square)
    assert not point_in_polygon(0.5, -0.1, square)


def test_zone_drops_places_inside_except_the_kept_ones(places, signals):
    zone = {
        "name": "Colosseum area",
        "polygon": [[41.889, 12.491], [41.889, 12.494], [41.892, 12.494], [41.892, 12.491]],
        "keep": [],
        "reason": "test",
    }
    curation = {"checked_on": "2026-10-17", "places": [], "exclude_within": [zone]}
    out, report = apply_curation(places, curation, signals)

    assert "osm:way/1" not in [p["id"] for p in out]
    assert report.excluded_by_zone == {"Colosseum area": 1}

    zone["keep"] = ["osm:way/1"]
    out, report = apply_curation(places, curation, signals)

    assert "osm:way/1" in [p["id"] for p in out]
    assert report.excluded_by_zone == {"Colosseum area": 0}


def test_zone_without_reason_is_rejected(tmp_path):
    path = _write(
        tmp_path,
        {
            "checked_on": "2026-10-17",
            "places": [],
            "exclude_within": [{"name": "x", "polygon": [[0, 0], [0, 1], [1, 1]]}],
        },
    )

    with pytest.raises(CurationError, match="polygon and a reason"):
        load_curation(path)


def test_low_confidence_entry_is_applied_as_inferred(places, signals):
    entry = _entry(confidence="low")
    out, report = apply_curation(places, {"checked_on": "2026-10-17", "places": [entry]}, signals)
    colosseum = next(p for p in out if p["id"] == "osm:way/1")

    assert colosseum["hours"]["confidence"] == "inferred"
    assert colosseum["cost"]["confidence"] == "inferred"
    assert report.applied[0]["as"] == "inferred"


def test_missing_pinned_id_falls_back_to_names(places, signals):
    entry = _entry(match={"id": "osm:way/999", "names": ["Colosseo"], "near": [41.8902, 12.4922]})

    assert find_match(entry, places, signals)["id"] == "osm:way/1"


def test_bad_confidence_value_is_rejected(tmp_path):
    path = _write(tmp_path, {"checked_on": "2026-10-17", "places": [_entry(confidence="sure")]})

    with pytest.raises(CurationError, match="confidence"):
        load_curation(path)
