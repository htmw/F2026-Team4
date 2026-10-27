"""Tests for merging duplicate records of the same place."""

from pathlib import Path

import pytest

from ingest.dedupe import dedupe, distance_m
from ingest.to_place import build_place, make_validator

M_PER_DEG_LAT = 111_195.0


def _hours(confidence):
    day = [["09:00", "18:00"]] if confidence != "unknown" else None
    hours = {d: day for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
    hours["confidence"] = confidence
    return hours


def _place(pid, name, lat, lon, cats=("museum",), hours="inferred", cost="unknown", pop=0.1):
    return {
        "id": pid,
        "name": name,
        "lat": lat,
        "lon": lon,
        "categories": list(cats),
        "typical_duration_minutes": 30,
        "cost": {"amount": 0.0, "currency": "EUR", "confidence": cost},
        "hours": _hours(hours),
        "source": "osm",
        "popularity": pop,
    }


def _signals(*places, wikidata=None, osm_type="node"):
    return {
        p["id"]: {"wikidata": wikidata, "documented": 1, "osm_type": osm_type, "names": []}
        for p in places
    }


def test_distance_m_matches_a_known_offset():
    a = {"lat": 41.9, "lon": 12.5}
    b = {"lat": 41.9 + 100 / M_PER_DEG_LAT, "lon": 12.5}

    assert distance_m(a, b) == pytest.approx(100, abs=0.5)


def test_same_name_close_together_is_merged_and_richer_copy_wins():
    node = _place("osm:node/1", "Museo X", 41.9, 12.5, hours="inferred", pop=0.2)
    way = _place(
        "osm:way/2", "Museo X", 41.9 + 30 / M_PER_DEG_LAT, 12.5,
        cats=("landmark",), hours="known", pop=0.6,
    )
    kept, report = dedupe([node, way], _signals(node, way))

    assert report.merged == 1
    assert len(kept) == 1
    assert kept[0]["id"] == "osm:way/2"
    assert kept[0]["categories"] == ["landmark", "museum"]
    # The museum category raises the visit length to the museum default.
    assert kept[0]["typical_duration_minutes"] == 90


def test_same_name_far_apart_is_kept_twice():
    a = _place("osm:node/1", "Bar Roma", 41.9, 12.5, cats=("bar",))
    b = _place("osm:node/2", "Bar Roma", 41.9 + 500 / M_PER_DEG_LAT, 12.5, cats=("bar",))
    kept, report = dedupe([a, b], _signals(a, b))

    assert report.merged == 0
    assert len(kept) == 2


def test_same_wikidata_merges_different_names_but_not_far_away():
    a = _place("osm:way/1", "Pantheon", 41.8986, 12.4769)
    b = _place("osm:node/2", "Basilica di Santa Maria ad Martyres", 41.8988, 12.4770)
    c = _place("osm:node/3", "Pantheon copy", 41.95, 12.60)  # about 11 km away
    signals = _signals(a, b, c, wikidata="Q99309")
    signals["osm:way/1"]["osm_type"] = "way"  # a polygon beats a node when all else is equal
    kept, report = dedupe([a, b, c], signals)

    assert report.merged == 1
    assert sorted(p["id"] for p in kept) == ["osm:node/3", "osm:way/1"]


def test_winner_borrows_known_hours_and_cost_from_a_copy():
    rich_hours = _place("osm:node/1", "Galleria", 41.9, 12.5, hours="known", pop=0.9)
    rich_cost = _place("osm:node/2", "Galleria", 41.9, 12.5, cost="known", pop=0.1)
    kept, _ = dedupe([rich_cost, rich_hours], _signals(rich_hours, rich_cost))

    assert kept[0]["id"] == "osm:node/1"
    assert kept[0]["hours"]["confidence"] == "known"
    assert kept[0]["cost"]["confidence"] == "known"
    assert kept[0]["popularity"] == 0.9


def _north(place_id, name, metres, **kwargs):
    return _place(place_id, name, 41.9 + metres / M_PER_DEG_LAT, 12.5, **kwargs)


def test_a_row_of_neighbours_does_not_chain_into_one_group():
    # 50 m apart each: B is close to A and to C, but C is 100 m from A.
    a = _north("osm:node/1", "Edicola", 0, pop=0.9)
    b = _north("osm:node/2", "Edicola", 50, pop=0.5)
    c = _north("osm:node/3", "Edicola", 100, pop=0.1)
    kept, report = dedupe([a, b, c], _signals(a, b, c))

    assert report.merged == 1
    assert sorted(p["id"] for p in kept) == ["osm:node/1", "osm:node/3"]


def test_shared_wikidata_with_other_names_needs_to_be_very_close():
    # The two fountains of St Peter's Square share one item and stand about 120 m apart.
    bernini = _north("osm:node/1", "Fontana di Bernini", 0, cats=("landmark",))
    maderno = _north("osm:node/2", "Fontana di Maderno", 120, cats=("landmark",))
    kept, report = dedupe([bernini, maderno], _signals(bernini, maderno, wikidata="Q3747467"))

    assert report.merged == 0
    assert len(kept) == 2


def test_shared_wikidata_with_the_same_name_merges_up_to_a_kilometre():
    gate = _north("osm:node/1", "Villa Ada", 0, cats=("park",), pop=0.2)
    park = _north("osm:way/2", "Villa Ada", 800, cats=("park",), pop=0.7)
    kept, report = dedupe([gate, park], _signals(gate, park, wikidata="Q1"))

    assert report.merged == 1
    assert kept[0]["id"] == "osm:way/2"


def test_same_name_with_different_wikidata_stays_apart():
    a = _north("osm:node/1", "San Lorenzo", 0, cats=("church",))
    b = _north("osm:node/2", "San Lorenzo", 30, cats=("church",))
    signals = _signals(a, b)
    signals["osm:node/1"]["wikidata"] = "Q1"
    signals["osm:node/2"]["wikidata"] = "Q2"
    kept, report = dedupe([a, b], signals)

    assert report.merged == 0
    assert len(kept) == 2


@pytest.mark.parametrize("wikidata", [None, "Q5"])
def test_a_venue_never_merges_with_a_sight(wikidata):
    palace = _north("osm:way/1", "Palazzo Rosso", 0, cats=("landmark",), pop=0.6)
    bar = _north("osm:node/2", "Palazzo Rosso", 15, cats=("bar",), hours="known", pop=0.1)
    kept, report = dedupe([palace, bar], _signals(palace, bar, wikidata=wikidata))

    assert report.merged == 0
    assert sorted(p["id"] for p in kept) == ["osm:node/2", "osm:way/1"]


# --- Walls and aqueducts mapped as many pieces ----------------------------------------


def _wall_signals(places, wikidata=None, rough=()):
    signals = _signals(*places, wikidata=wikidata, osm_type="way")
    for p in places:
        signals[p["id"]]["long_structure"] = True
        signals[p["id"]]["osm_type"] = p["id"].split(":")[1].split("/")[0]
        signals[p["id"]]["rough_point"] = p["id"] in rough
    return signals


def test_wall_pieces_across_the_city_become_one_stop_placed_on_a_piece():
    # The ring relation sits at the centre of its bounding box, next to the Colosseum.
    ring = _place(
        "osm:relation/1", "Mura Aureliane", 41.8930, 12.4922, cats=("landmark",), pop=0.67
    )
    pieces = [
        _north("osm:way/2", "Mura Aureliane", 1800, cats=("landmark",), pop=0.53),
        _north("osm:way/3", "Mura Aureliane", 4000, cats=("landmark",), pop=0.20),
        _north("osm:way/4", "Mura Aureliane", 6000, cats=("landmark",), pop=0.10),
    ]
    signals = _wall_signals([ring, *pieces], wikidata="Q625149", rough={"osm:relation/1"})
    kept, report = dedupe([ring, *pieces], signals)

    assert [p["id"] for p in kept] == ["osm:relation/1"]
    wall = kept[0]
    assert (wall["lat"], wall["lon"]) == (pieces[0]["lat"], pieces[0]["lon"])
    assert wall["popularity"] == 0.67
    assert report.merged == 3
    assert report.long_structures == [
        {"kept": "osm:relation/1", "name": "Mura Aureliane", "pieces": 4, "placed_at": "osm:way/2"}
    ]


def test_ruins_sharing_the_wall_wikidata_join_the_wall_but_venues_do_not():
    piece = _north("osm:way/1", "Mura Serviane", 0, cats=("landmark",), pop=0.5)
    ruins = _north("osm:way/2", "Resti di Mura Serviane", 2500, cats=("landmark",), pop=0.3)
    bar = _north("osm:node/3", "Mura Serviane", 20, cats=("bar",))
    signals = _wall_signals([piece])
    signals["osm:way/1"]["wikidata"] = "Q281330"
    signals.update(_signals(ruins, wikidata="Q281330", osm_type="way"))
    signals.update(_signals(bar))
    kept, report = dedupe([piece, ruins, bar], signals)

    assert sorted(p["id"] for p in kept) == ["osm:node/3", "osm:way/1"]
    assert report.long_structures[0]["pieces"] == 2


def test_a_wall_known_only_as_a_collection_relation_is_dropped():
    site = _place("osm:relation/1", "Mura di Roma", 41.8930, 12.4880, cats=("landmark",))
    signals = _wall_signals([site], rough={"osm:relation/1"})
    kept, report = dedupe([site], signals)

    assert kept == []
    assert report.no_position == ["osm:relation/1"]


def test_a_wall_mapped_as_one_area_keeps_its_own_position():
    passetto = _place("osm:relation/1", "Passetto di Borgo", 41.9033, 12.4611, cats=("landmark",))
    kept, report = dedupe([passetto], _wall_signals([passetto]))

    assert kept == [passetto]
    assert report.no_position == []


def test_result_does_not_depend_on_input_order():
    a = _place("osm:node/1", "Fontana", 41.9, 12.5, pop=0.3)
    b = _place("osm:node/2", "Fontana", 41.9, 12.5, pop=0.3)
    first, _ = dedupe([a, b], _signals(a, b))
    second, _ = dedupe([b, a], _signals(a, b))

    assert first == second
    assert first[0]["id"] == "osm:node/1"


def test_records_still_merge_when_only_one_has_an_english_name():
    schema = Path(__file__).resolve().parents[2] / "contracts" / "place.schema.json"
    validator = make_validator(schema)
    tagged = {"name": "Colosseo", "name:en": "Colosseum", "tourism": "museum"}
    plain = {"name": "Colosseo", "tourism": "museum"}
    places, signals = [], {}
    for i, tags in enumerate([tagged, plain], start=1):
        el = {"type": "node", "id": i, "lat": 41.8902, "lon": 12.4922 + i * 0.0001, "tags": tags}
        r = build_place(el, currency="EUR", fetched_date="2026-10-27", validator=validator)
        places.append(r.place)
        signals[r.place["id"]] = r.signals

    merged, _ = dedupe(places, signals)

    assert [p["name"] for p in merged] == ["Colosseum"]
