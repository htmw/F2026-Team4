"""Tests for trip state: saving planned trips, fetching them, and re-planning on feedback."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.contracts import validate
from api.main import Feedback, _merge_feedback, app

ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def _plan() -> dict:
    body = {
        "profile": json.loads((ROOT / "fixtures" / "sample.profile.json").read_text()),
        "destination": {"name": "Lisbon", "country": "PT", "lat": 38.72, "lon": -9.14},
        "start_date": "2026-10-01",
        "end_date": "2026-10-03",
    }
    resp = client.post("/plan", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _place_ids(itinerary: dict) -> set[str]:
    return {item["place_id"] for day in itinerary["days"] for item in day["items"]}


def test_planned_trip_can_be_fetched():
    itinerary = _plan()
    resp = client.get(f"/trips/{itinerary['trip_id']}")
    assert resp.status_code == 200
    assert resp.json() == itinerary


def test_unknown_trip_is_404():
    assert client.get("/trips/does-not-exist").status_code == 404
    assert client.post("/trips/does-not-exist/feedback", json={}).status_code == 404


def test_rejected_place_is_dropped_on_replan():
    itinerary = _plan()
    rejected = sorted(_place_ids(itinerary))[0]

    resp = client.post(f"/trips/{itinerary['trip_id']}/feedback", json={"rejected": [rejected]})
    assert resp.status_code == 200, resp.text
    replanned = resp.json()

    assert validate("itinerary", replanned) == []
    assert replanned["trip_id"] == itinerary["trip_id"]
    assert rejected not in _place_ids(replanned)
    # The re-planned version is what the trip now returns.
    assert client.get(f"/trips/{itinerary['trip_id']}").json() == replanned


def test_rejections_accumulate_across_feedback_calls():
    itinerary = _plan()
    first, second = sorted(_place_ids(itinerary))[:2]
    trip = f"/trips/{itinerary['trip_id']}/feedback"

    client.post(trip, json={"rejected": [first]})
    replanned = client.post(trip, json={"rejected": [second]}).json()

    assert first not in _place_ids(replanned)
    assert second not in _place_ids(replanned)


def test_place_cannot_be_accepted_and_rejected_at_once():
    itinerary = _plan()
    resp = client.post(
        f"/trips/{itinerary['trip_id']}/feedback",
        json={"accepted": ["osm:node/1"], "rejected": ["osm:node/1"]},
    )
    assert resp.status_code == 422


def test_newest_feedback_decision_wins():
    current = {"accepted": ["a", "b"], "rejected": ["c"]}
    merged = _merge_feedback(current, Feedback(accepted=["c"], rejected=["a"]))
    assert merged == {"accepted": ["b", "c"], "rejected": ["a"]}


# ---- swap a stop / add a place ---------------------------------------------------------


def test_suggestions_for_a_swap_leave_out_the_trip_and_follow_the_contract():
    itinerary = _plan()
    swapped_out = itinerary["days"][-1]["items"][0]["place_id"]

    resp = client.get(f"/trips/{itinerary['trip_id']}/suggestions", params={"replace": swapped_out})

    assert resp.status_code == 200, resp.text
    found = resp.json()["suggestions"]
    assert 1 <= len(found) <= 5
    assert not {s["place_id"] for s in found} & _place_ids(itinerary)
    for s in found:
        assert set(s) == {"place_id", "name", "reason", "cost", "cost_confidence"}
        assert s["reason"].startswith("Matches your interest")


def test_suggestions_for_an_unknown_trip_or_a_bad_date():
    resp = client.get("/trips/does-not-exist/suggestions")
    assert resp.status_code == 404
    assert "No trip with id" in resp.text

    itinerary = _plan()
    resp = client.get(f"/trips/{itinerary['trip_id']}/suggestions", params={"date": "12/02/2026"})
    assert resp.status_code == 422


def test_a_swapped_in_place_is_planned_on_the_day_it_replaces():
    itinerary = _plan()
    last_day = itinerary["days"][-1]
    swapped_out = last_day["items"][0]["place_id"]
    trip = f"/trips/{itinerary['trip_id']}"
    chosen = client.get(f"{trip}/suggestions", params={"replace": swapped_out}).json()
    new_place = chosen["suggestions"][0]["place_id"]

    swap = {"accepted": [new_place], "rejected": [swapped_out]}
    resp = client.post(f"{trip}/feedback", json=swap)

    assert resp.status_code == 200, resp.text
    replanned = resp.json()
    assert validate("itinerary", replanned) == []
    assert swapped_out not in _place_ids(replanned)
    placed_on = [d["date"] for d in replanned["days"]
                 if any(i["place_id"] == new_place for i in d["items"])]
    assert placed_on == [last_day["date"]]


def test_an_added_place_is_planned():
    itinerary = _plan()
    trip = f"/trips/{itinerary['trip_id']}"
    chosen = client.get(f"{trip}/suggestions", params={"date": itinerary["days"][1]["date"]})
    new_place = chosen.json()["suggestions"][0]["place_id"]

    resp = client.post(f"{trip}/feedback", json={"accepted": [new_place]})

    assert resp.status_code == 200, resp.text
    assert new_place in _place_ids(resp.json())
