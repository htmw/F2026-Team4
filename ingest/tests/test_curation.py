"""Tests for applying hand checked facts on top of OSM records."""

import json
from pathlib import Path

import pytest

from ingest.curation import CurationError, apply_curation, find_match, load_curation
from ingest.to_place import make_validator

SCHEMA = Path(__file__).resolve().parents[2] / "contracts" / "place.schema.json"


def _place(pid, name, lat, lon, pop=0.5, cats=("landmark",)):
    hours = {d: [["00:00", "23:59"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
    hours["confidence"] = "inferred"
    return {
        "id": pid,
        "name": name,
        "lat": lat,
        "lon": lon,
        "categories": list(cats),
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


# --- Copies of a curated place --------------------------------------------------------

ARA_PACIS = [41.9062, 12.4755]


def _ara_pacis_places():
    return [
        _place("osm:way/10", "Museo dell'Ara Pacis", 41.9062, 12.4755, pop=0.43, cats=("museum",)),
        # The altar inside the museum, mapped as its own sight 6 m away.
        _place("osm:way/11", "Ara Pacis Augustae", 41.90625, 12.4755, pop=0.41),
        _place("osm:node/12", "Bar Ara Pacis", 41.9063, 12.4757, pop=0.0, cats=("bar",)),
        _place("osm:node/13", "Ara Pacis Augustae", 41.93, 12.50, pop=0.1),  # 3 km away
    ]


def _ara_pacis_entry(**overrides):
    entry = _entry(
        name="Ara Pacis Museum",
        match={"names": ["Museo dell'Ara Pacis", "Ara Pacis Augustae", "Bar Ara Pacis"],
               "near": ARA_PACIS},
        price={"amount": 14.0, "currency": "EUR"},
        duration_minutes=60,
    )
    entry.update(overrides)
    return entry


def test_copies_of_a_curated_place_are_folded_into_it():
    places = _ara_pacis_places()
    curation = {"checked_on": "2026-10-17", "places": [_ara_pacis_entry()]}
    out, report = apply_curation(places, curation, {}, make_validator(SCHEMA))
    ids = [p["id"] for p in out]

    assert "osm:way/11" not in ids
    assert report.folded == [
        {"entry": "Ara Pacis Museum", "kept": "osm:way/10", "dropped": ["osm:way/11"]}
    ]
    museum = next(p for p in out if p["id"] == "osm:way/10")
    assert museum["categories"] == ["museum", "landmark"]
    assert museum["cost"]["amount"] == 14.0
    assert museum["typical_duration_minutes"] == 60
    # A venue with the same name stays, and so does a namesake outside the radius.
    assert "osm:node/12" in ids
    assert "osm:node/13" in ids


def test_a_copy_that_another_entry_is_about_is_not_folded():
    places = _ara_pacis_places()
    altar = _entry(
        name="Altar",
        match={"names": ["Ara Pacis Augustae"], "near": ARA_PACIS, "radius_m": 50},
    )
    museum = _ara_pacis_entry(match={"names": ["Museo dell'Ara Pacis", "Ara Pacis Augustae"],
                                     "near": ARA_PACIS})
    curation = {"checked_on": "2026-10-17", "places": [museum, altar]}
    out, report = apply_curation(places, curation, {})

    assert {"osm:way/10", "osm:way/11"} <= {p["id"] for p in out}
    assert report.folded == []


def test_two_entries_for_one_place_are_an_error(places, signals):
    curation = {"checked_on": "2026-10-17", "places": [_entry(), _entry(name="Colosseo again")]}

    with pytest.raises(CurationError, match="both match osm:way/1"):
        apply_curation(places, curation, signals)


def test_zone_keeps_a_neighbourhood_whose_label_falls_inside(signals):
    places = [
        _place("osm:way/1", "Tempio di Saturno", 41.8925, 12.4845),
        _place("osm:relation/2", "Campitelli", 41.8926, 12.4846, cats=("neighborhood",)),
    ]
    zone = {
        "name": "Forum",
        "polygon": [[41.891, 12.483], [41.891, 12.486], [41.894, 12.486], [41.894, 12.483]],
        "keep": [],
        "reason": "test",
    }
    out, report = apply_curation(
        places, {"checked_on": "2026-10-17", "places": [], "exclude_within": [zone]}, {}
    )

    assert [p["id"] for p in out] == ["osm:relation/2"]
    assert report.excluded_by_zone == {"Forum": 1}
