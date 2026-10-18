"""Tests for merging duplicate records of the same place."""

import pytest

from ingest.dedupe import dedupe, distance_m

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


def test_result_does_not_depend_on_input_order():
    a = _place("osm:node/1", "Fontana", 41.9, 12.5, pop=0.3)
    b = _place("osm:node/2", "Fontana", 41.9, 12.5, pop=0.3)
    first, _ = dedupe([a, b], _signals(a, b))
    second, _ = dedupe([b, a], _signals(a, b))

    assert first == second
    assert first[0]["id"] == "osm:node/1"
