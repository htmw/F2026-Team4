"""Tests for merging duplicate records of the same place."""

import pytest

from ingest.dedupe import dedupe, distance_m

M_PER_DEG_LAT = 111_195.0
# A point in central Lisbon. Test places are put north of it at a given distance.
BASE_LAT, BASE_LON = 38.72, -9.14


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


def _north(place_id, name, metres, **kwargs):
    return _place(place_id, name, BASE_LAT + metres / M_PER_DEG_LAT, BASE_LON, **kwargs)


def test_distance_m_matches_a_known_offset():
    a = {"lat": BASE_LAT, "lon": BASE_LON}
    b = {"lat": BASE_LAT + 100 / M_PER_DEG_LAT, "lon": BASE_LON}

    assert distance_m(a, b) == pytest.approx(100, abs=0.5)


def test_same_name_close_together_is_merged_and_richer_copy_wins():
    node = _north("osm:node/1", "Museu X", 0, hours="inferred", pop=0.2)
    way = _north("osm:way/2", "Museu X", 30, cats=("landmark",), hours="known", pop=0.6)
    kept, report = dedupe([node, way], _signals(node, way))

    assert report.merged == 1
    assert len(kept) == 1
    assert kept[0]["id"] == "osm:way/2"
    # The most specific category comes first, whichever record it came from.
    assert kept[0]["categories"] == ["museum", "landmark"]
    # The museum category raises the visit length to the museum default.
    assert kept[0]["typical_duration_minutes"] == 90


def test_defaults_follow_the_more_specific_category_of_a_copy():
    # Like the Jeronimos Monastery: the richest record says landmark (open all day, free),
    # a copy says museum. The merged place is a museum with museum default hours, and its
    # price is unknown rather than assumed free.
    landmark = _north("osm:relation/1", "Mosteiro dos Jerónimos", 0, cats=("landmark",), pop=0.7)
    days = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    landmark["hours"] = {**{d: [["00:00", "23:59"]] for d in days}, "confidence": "inferred"}
    landmark["cost"]["confidence"] = "inferred"
    museum = _north("osm:node/2", "Mosteiro dos Jerónimos", 20, cats=("museum",), pop=0.1)
    kept, _ = dedupe([landmark, museum], _signals(landmark, museum))

    assert kept[0]["id"] == "osm:relation/1"
    assert kept[0]["categories"] == ["museum", "landmark"]
    assert kept[0]["hours"]["mon"] == [["10:00", "18:00"]]
    assert kept[0]["hours"]["confidence"] == "inferred"
    assert kept[0]["cost"]["confidence"] == "unknown"


def test_same_name_far_apart_is_kept_twice():
    a = _north("osm:node/1", "Tasca do Bairro", 0, cats=("bar",))
    b = _north("osm:node/2", "Tasca do Bairro", 500, cats=("bar",))
    kept, report = dedupe([a, b], _signals(a, b))

    assert report.merged == 0
    assert len(kept) == 2


def test_same_wikidata_merges_different_names_but_not_far_away():
    # The National Pantheon is housed in the church of Santa Engracia: one place, two names.
    a = _place("osm:way/1", "Panteão Nacional", 38.7148, -9.1249)
    b = _place("osm:node/2", "Igreja de Santa Engrácia", 38.7150, -9.1248)
    c = _place("osm:node/3", "Panteão Nacional", 38.7800, -9.0500)  # about 10 km away
    signals = _signals(a, b, c, wikidata="Q1001")
    signals["osm:way/1"]["osm_type"] = "way"  # a polygon beats a node when all else is equal
    kept, report = dedupe([a, b, c], signals)

    assert report.merged == 1
    assert sorted(p["id"] for p in kept) == ["osm:node/3", "osm:way/1"]


def test_winner_borrows_known_hours_and_cost_from_a_copy():
    rich_hours = _north("osm:node/1", "Galeria", 0, hours="known", pop=0.9)
    rich_cost = _north("osm:node/2", "Galeria", 0, cost="known", pop=0.1)
    kept, _ = dedupe([rich_cost, rich_hours], _signals(rich_hours, rich_cost))

    assert kept[0]["id"] == "osm:node/1"
    assert kept[0]["hours"]["confidence"] == "known"
    assert kept[0]["cost"]["confidence"] == "known"
    assert kept[0]["popularity"] == 0.9


def test_a_row_of_neighbours_does_not_chain_into_one_group():
    # 50 m apart each: B is close to A and to C, but C is 100 m from A.
    a = _north("osm:node/1", "Quiosque", 0, pop=0.9)
    b = _north("osm:node/2", "Quiosque", 50, pop=0.5)
    c = _north("osm:node/3", "Quiosque", 100, pop=0.1)
    kept, report = dedupe([a, b, c], _signals(a, b, c))

    assert report.merged == 1
    assert sorted(p["id"] for p in kept) == ["osm:node/1", "osm:node/3"]


def test_shared_wikidata_with_other_names_needs_to_be_very_close():
    # Two fountains on one square can share one wikidata item and stand 120 m apart.
    north = _north("osm:node/1", "Fonte do Rossio Norte", 0, cats=("landmark",))
    south = _north("osm:node/2", "Fonte do Rossio Sul", 120, cats=("landmark",))
    kept, report = dedupe([north, south], _signals(north, south, wikidata="Q1002"))

    assert report.merged == 0
    assert len(kept) == 2


def test_shared_wikidata_with_the_same_name_merges_up_to_a_kilometre():
    gate = _north("osm:node/1", "Parque Eduardo VII", 0, cats=("park",), pop=0.2)
    park = _north("osm:way/2", "Parque Eduardo VII", 800, cats=("park",), pop=0.7)
    kept, report = dedupe([gate, park], _signals(gate, park, wikidata="Q1003"))

    assert report.merged == 1
    assert kept[0]["id"] == "osm:way/2"


def test_same_name_with_different_wikidata_stays_apart():
    a = _north("osm:node/1", "Capela de Santo António", 0, cats=("church",))
    b = _north("osm:node/2", "Capela de Santo António", 30, cats=("church",))
    signals = _signals(a, b)
    signals["osm:node/1"]["wikidata"] = "Q1004"
    signals["osm:node/2"]["wikidata"] = "Q1005"
    kept, report = dedupe([a, b], signals)

    assert report.merged == 0
    assert len(kept) == 2


@pytest.mark.parametrize("wikidata", [None, "Q1006"])
def test_a_venue_never_merges_with_a_sight(wikidata):
    palace = _north("osm:way/1", "Palácio Foz", 0, cats=("landmark",), pop=0.6)
    bar = _north("osm:node/2", "Palácio Foz", 15, cats=("bar",), hours="known", pop=0.1)
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
    # The relation that groups the wall sits at the centre of its bounding box, in the
    # middle of the old town, away from every piece of the wall.
    ring = _north("osm:relation/1", "Cerca Fernandina", -900, cats=("landmark",), pop=0.67)
    pieces = [
        _north("osm:way/2", "Cerca Fernandina", 1800, cats=("landmark",), pop=0.53),
        _north("osm:way/3", "Cerca Fernandina", 4000, cats=("landmark",), pop=0.20),
        _north("osm:way/4", "Cerca Fernandina", 6000, cats=("landmark",), pop=0.10),
    ]
    signals = _wall_signals([ring, *pieces], wikidata="Q1007", rough={"osm:relation/1"})
    kept, report = dedupe([ring, *pieces], signals)

    assert [p["id"] for p in kept] == ["osm:relation/1"]
    wall = kept[0]
    assert (wall["lat"], wall["lon"]) == (pieces[0]["lat"], pieces[0]["lon"])
    assert wall["popularity"] == 0.67
    assert report.merged == 3
    assert report.long_structures == [
        {
            "kept": "osm:relation/1",
            "name": "Cerca Fernandina",
            "pieces": 4,
            "placed_at": "osm:way/2",
        }
    ]


def test_ruins_sharing_the_wall_wikidata_join_the_wall_but_venues_do_not():
    piece = _north("osm:way/1", "Cerca Moura", 0, cats=("landmark",), pop=0.5)
    ruins = _north("osm:way/2", "Troço da Cerca Moura", 2500, cats=("landmark",), pop=0.3)
    bar = _north("osm:node/3", "Cerca Moura", 20, cats=("bar",))
    signals = _wall_signals([piece])
    signals["osm:way/1"]["wikidata"] = "Q1008"
    signals.update(_signals(ruins, wikidata="Q1008", osm_type="way"))
    signals.update(_signals(bar))
    kept, report = dedupe([piece, ruins, bar], signals)

    assert sorted(p["id"] for p in kept) == ["osm:node/3", "osm:way/1"]
    assert report.long_structures[0]["pieces"] == 2


def test_a_wall_known_only_as_a_collection_relation_is_dropped():
    site = _north("osm:relation/1", "Muralhas de Lisboa", 0, cats=("landmark",))
    signals = _wall_signals([site], rough={"osm:relation/1"})
    kept, report = dedupe([site], signals)

    assert kept == []
    assert report.no_position == ["osm:relation/1"]


def test_a_wall_mapped_as_one_area_keeps_its_own_position():
    # In the Lisbon data the Aqueduto das Necessidades is one area relation like this.
    aqueduct = _place(
        "osm:relation/1", "Aqueduto das Necessidades", 38.7090, -9.1690, cats=("landmark",)
    )
    kept, report = dedupe([aqueduct], _wall_signals([aqueduct]))

    assert kept == [aqueduct]
    assert report.no_position == []


def test_result_does_not_depend_on_input_order():
    a = _north("osm:node/1", "Chafariz", 0, pop=0.3)
    b = _north("osm:node/2", "Chafariz", 0, pop=0.3)
    first, _ = dedupe([a, b], _signals(a, b))
    second, _ = dedupe([b, a], _signals(a, b))

    assert first == second
    assert first[0]["id"] == "osm:node/1"
