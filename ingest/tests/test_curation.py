"""Tests for applying hand checked facts on top of OSM records.

The places and prices below are test values in Lisbon, not checked facts.
"""

import json
from pathlib import Path

import pytest

from ingest.curation import CurationError, apply_curation, find_match, load_curation
from ingest.to_place import make_validator

SCHEMA = Path(__file__).resolve().parents[2] / "contracts" / "place.schema.json"
BELEM_TOWER = [38.6916, -9.2160]


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
        _place("osm:way/1", "Torre de Belém", *BELEM_TOWER, pop=1.0),
        _place("osm:node/2", "Panteão Nacional", 38.7148, -9.1249, pop=0.9),
        _place("osm:node/3", "Torre de Belém", 38.7500, -9.1500, pop=0.1),  # a bar far away
    ]


@pytest.fixture
def signals():
    return {
        "osm:way/1": {"names": ["belem tower", "torre de belem", "torre de sao vicente"]},
        "osm:node/2": {"names": ["panteao nacional"]},
        "osm:node/3": {"names": ["torre de belem"]},
    }


def _entry(**overrides):
    entry = {
        "name": "Belem Tower",
        "match": {"names": ["Torre de Belém"], "near": BELEM_TOWER, "radius_m": 300},
        "opening_hours": "Tu-Su 10:00-17:30",
        "price": {"amount": 15.0, "currency": "EUR"},
        "duration_minutes": 60,
        "sources": ["https://example.org/belem-tower"],
    }
    entry.update(overrides)
    return entry


def _write(tmp_path, data):
    path = tmp_path / "lisbon.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_curated_facts_become_known_and_stay_valid(places, signals):
    curation = {"checked_on": "2026-10-17", "places": [_entry()]}
    out, report = apply_curation(places, curation, signals, make_validator(SCHEMA))
    tower = next(p for p in out if p["id"] == "osm:way/1")

    assert report.unmatched == []
    assert tower["hours"]["confidence"] == "known"
    assert tower["hours"]["mon"] is None  # closed on Mondays
    assert tower["hours"]["tue"] == [["10:00", "17:30"]]
    assert tower["cost"] == {"amount": 15.0, "currency": "EUR", "confidence": "known"}
    assert tower["typical_duration_minutes"] == 60
    assert tower["source"] == "osm+curated"
    assert tower["last_verified"] == "2026-10-17"
    # The input list is left alone.
    assert places[0]["hours"]["confidence"] == "inferred"


def test_match_uses_other_language_names_and_distance(places, signals):
    entry = _entry(match={"names": ["Torre de São Vicente"], "near": BELEM_TOWER})

    assert find_match(entry, places, signals)["id"] == "osm:way/1"


def test_entry_too_far_from_any_match_is_reported(places, signals):
    entry = _entry(match={"names": ["Torre de Belém"], "near": [38.65, -9.30], "radius_m": 200})
    _, report = apply_curation(places, {"checked_on": "2026-10-17", "places": [entry]}, signals)

    assert report.unmatched == ["Belem Tower"]


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
        ({"opening_hours": "Tu-Su 10:00-17:30 (last entry 17:00)"}, "cannot be parsed"),
        ({"price": {"amount": 15, "currency": "EURO"}}, "ISO 4217"),
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

    assert load_curation(path)["places"][0]["name"] == "Belem Tower"


def test_point_in_polygon_square():
    from ingest.curation import point_in_polygon

    square = [[0, 0], [0, 1], [1, 1], [1, 0]]

    assert point_in_polygon(0.5, 0.5, square)
    assert not point_in_polygon(1.5, 0.5, square)
    assert not point_in_polygon(0.5, -0.1, square)


def test_zone_drops_places_inside_except_the_kept_ones(places, signals):
    zone = {
        "name": "Belem Tower area",
        "polygon": [[38.691, -9.217], [38.691, -9.215], [38.692, -9.215], [38.692, -9.217]],
        "keep": [],
        "reason": "test",
    }
    curation = {"checked_on": "2026-10-17", "places": [], "exclude_within": [zone]}
    out, report = apply_curation(places, curation, signals)

    assert "osm:way/1" not in [p["id"] for p in out]
    assert report.excluded_by_zone == {"Belem Tower area": 1}

    zone["keep"] = ["osm:way/1"]
    out, report = apply_curation(places, curation, signals)

    assert "osm:way/1" in [p["id"] for p in out]
    assert report.excluded_by_zone == {"Belem Tower area": 0}


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
    tower = next(p for p in out if p["id"] == "osm:way/1")

    assert tower["hours"]["confidence"] == "inferred"
    assert tower["cost"]["confidence"] == "inferred"
    assert report.applied[0]["as"] == "inferred"


def test_missing_pinned_id_falls_back_to_names(places, signals):
    entry = _entry(match={"id": "osm:way/999", "names": ["Torre de Belém"], "near": BELEM_TOWER})

    assert find_match(entry, places, signals)["id"] == "osm:way/1"


def test_bad_confidence_value_is_rejected(tmp_path):
    path = _write(tmp_path, {"checked_on": "2026-10-17", "places": [_entry(confidence="sure")]})

    with pytest.raises(CurationError, match="confidence"):
        load_curation(path)


# --- Copies of a curated place --------------------------------------------------------

JERONIMOS = [38.6979, -9.2068]


def _jeronimos_places():
    return [
        _place("osm:way/10", "Mosteiro dos Jerónimos", *JERONIMOS, pop=0.43, cats=("museum",)),
        # The church inside the monastery, mapped as its own sight 6 m away.
        _place("osm:way/11", "Igreja de Santa Maria de Belém", 38.69795, -9.2068, pop=0.41),
        _place("osm:node/12", "Bar dos Jerónimos", 38.6980, -9.2070, pop=0.0, cats=("bar",)),
        # A namesake 3 km away.
        _place("osm:node/13", "Igreja de Santa Maria de Belém", 38.7200, -9.1900, pop=0.1),
    ]


def _jeronimos_entry(**overrides):
    entry = _entry(
        name="Jeronimos Monastery",
        match={
            "names": [
                "Mosteiro dos Jerónimos",
                "Igreja de Santa Maria de Belém",
                "Bar dos Jerónimos",
            ],
            "near": JERONIMOS,
        },
        price={"amount": 18.0, "currency": "EUR"},
        duration_minutes=90,
    )
    entry.update(overrides)
    return entry


def test_copies_of_a_curated_place_are_folded_into_it():
    places = _jeronimos_places()
    curation = {"checked_on": "2026-10-17", "places": [_jeronimos_entry()]}
    out, report = apply_curation(places, curation, {}, make_validator(SCHEMA))
    ids = [p["id"] for p in out]

    assert "osm:way/11" not in ids
    assert report.folded == [
        {"entry": "Jeronimos Monastery", "kept": "osm:way/10", "dropped": ["osm:way/11"]}
    ]
    monastery = next(p for p in out if p["id"] == "osm:way/10")
    assert monastery["categories"] == ["museum", "landmark"]
    assert monastery["cost"]["amount"] == 18.0
    assert monastery["typical_duration_minutes"] == 90
    # A venue with the same name stays, and so does a namesake outside the radius.
    assert "osm:node/12" in ids
    assert "osm:node/13" in ids


def test_a_copy_that_another_entry_is_about_is_not_folded():
    places = _jeronimos_places()
    church = _entry(
        name="Church",
        match={"names": ["Igreja de Santa Maria de Belém"], "near": JERONIMOS, "radius_m": 50},
    )
    monastery = _jeronimos_entry(
        match={
            "names": ["Mosteiro dos Jerónimos", "Igreja de Santa Maria de Belém"],
            "near": JERONIMOS,
        }
    )
    curation = {"checked_on": "2026-10-17", "places": [monastery, church]}
    out, report = apply_curation(places, curation, {})

    assert {"osm:way/10", "osm:way/11"} <= {p["id"] for p in out}
    assert report.folded == []


def test_two_entries_for_one_place_are_an_error(places, signals):
    curation = {
        "checked_on": "2026-10-17",
        "places": [_entry(), _entry(name="Belem Tower again")],
    }

    with pytest.raises(CurationError, match="both match osm:way/1"):
        apply_curation(places, curation, signals)


def test_zone_keeps_a_neighbourhood_whose_label_falls_inside(signals):
    places = [
        _place("osm:way/1", "Ruínas do Paço da Alcáçova", 38.7138, -9.1336),
        _place("osm:relation/2", "Castelo", 38.7139, -9.1337, cats=("neighborhood",)),
    ]
    zone = {
        "name": "Castelo de São Jorge",
        "polygon": [[38.713, -9.135], [38.713, -9.132], [38.715, -9.132], [38.715, -9.135]],
        "keep": [],
        "reason": "test",
    }
    out, report = apply_curation(
        places, {"checked_on": "2026-10-17", "places": [], "exclude_within": [zone]}, {}
    )

    assert [p["id"] for p in out] == ["osm:relation/2"]
    assert report.excluded_by_zone == {"Castelo de São Jorge": 1}
