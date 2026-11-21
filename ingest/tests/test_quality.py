"""The data quality report measures what a traveler gets from a planned trip."""

import os
from datetime import date
from types import SimpleNamespace

from ingest import catalog, quality

ITINERARY = {
    "destination": {"name": "Porto, Portugal"},
    "totals": {"currency": "EUR", "walking_minutes": 20},
    "days": [{"items": [
        {"place_id": "a", "confidence": "known", "cost_confidence": "known",
         "description": "A tower.", "description_source": "wikipedia",
         "open_hours": [["09:00", "18:00"]]},
        {"place_id": "b", "confidence": "inferred", "cost_confidence": "inferred",
         "description": "Café.", "description_source": "openstreetmap",
         "travel_from_prev": {"minutes": 19, "mode": "transit", "walk_minutes": 4}},
    ]}],
}


def test_plan_stats_counts_what_the_traveler_sees():
    s = quality.plan_stats(ITINERARY)

    assert s["stops"] == 2
    assert (s["hours_verified"], s["hours_estimated"], s["hours_unknown"]) == (0.5, 0.5, 0.0)
    assert (s["price_real"], s["price_estimated"], s["price_unknown"]) == (0.5, 0.5, 0.0)
    assert (s["described"], s["from_wikipedia"]) == (1.0, 0.5)
    assert "with_photo" not in s, "photos were dropped from the plan, so no empty column"
    assert s["transit_rides"] == 1 and s["ride_walk_minutes"] == [4]


def test_city_stats_measures_the_walk_to_transit():
    places = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    s = quality.city_stats(places, {"a": 2.0, "b": 9.0})

    assert s == {"places": 3, "with_stop_walk": 2, "median_walk_to_stop": 5.5, "near_a_stop": 0.5}


def test_a_city_without_stop_data_says_so():
    assert quality.city_stats([{"id": "a"}], {})["median_walk_to_stop"] is None


def test_measure_and_render(monkeypatch):
    city = SimpleNamespace(places=[{"id": "a"}, {"id": "b"}], source="snapshot", path=".")
    monkeypatch.setattr(catalog, "_STOP_WALKS", {"a": 3.0, "b": 4.0, "elsewhere": 30.0})
    r = quality.measure("Porto", date(2026, 12, 1), plan=lambda **kw: ITINERARY,
                        load=lambda name: city)

    assert r["city"] == "Porto, Portugal" and r["places"] == 2
    assert r["median_walk_to_stop"] == 3.5, "only this city's places"
    md = quality.render({"Porto": r, "Atlantisville": {"error": "not found"}}, "2026-12-01")
    assert "| Porto, Portugal | 2 | 50% | 50% | 0% | 50% | 50% | 0% | 100% | 50% |" in md
    assert "- Atlantisville: not found" in md
    assert "no planned stop has unknown hours or prices" in md
    assert "(saved in the repo)" in md


def test_the_summary_line_matches_the_results():
    """Bala's review: with unknowns, the summary still said every stop was known or estimated."""
    clean = dict(quality.plan_stats(ITINERARY), city="Porto, Portugal", places=2, source="live",
                 load_seconds=1.0, with_stop_walk=0, median_walk_to_stop=None, near_a_stop=None)
    gappy = dict(clean, city="Lima, Peru", hours_unknown=0.2, price_unknown=0.0)

    all_known = quality.render({"Porto": clean}, "2026-12-01")
    assert "no planned stop has unknown hours or prices" in all_known

    some_unknown = quality.render({"Porto": clean, "Lima": gappy}, "2026-12-01")
    assert "every stop has a verified value" not in some_unknown
    assert "In 1 of 2 cities some planned stops have unknown hours or prices" in some_unknown
    assert "Lima, Peru (20% of stops with unknown hours, 0% with an unknown price)" in some_unknown


def test_downloaded_means_the_city_was_written_during_this_load_not_that_it_was_slow(tmp_path):
    """Bala's review: "saved" or "fresh" was guessed from the load time."""
    import time as clock

    places_file = tmp_path / "places.json"
    places_file.write_text("[]")
    old = clock.time() - 3600
    os.utime(places_file, (old, old))
    city = SimpleNamespace(source="live", path=tmp_path)

    began = clock.time()
    assert not quality.downloaded_during_load(city, began), "read from data/live, even if slow"

    places_file.write_text("[]")  # what a fetch does
    assert quality.downloaded_during_load(city, began)
    snapshot = SimpleNamespace(source="snapshot", path=tmp_path)
    assert not quality.downloaded_during_load(snapshot, began), "the repo copy is never fetched"


def test_the_report_names_where_each_city_came_from():
    assert quality._loaded_from({"source": "live", "downloaded": True}) == "downloaded now"
    assert quality._loaded_from({"source": "live", "downloaded": False}) == (
        "saved copy from an earlier fetch")
    assert quality._loaded_from({"source": "snapshot"}) == "saved in the repo"
