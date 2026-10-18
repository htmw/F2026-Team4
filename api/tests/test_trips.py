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
