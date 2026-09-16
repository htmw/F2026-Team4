"""Tests for the stub API and contracts.

These are the guardrails that keep `main` green: if a change breaks a contract
or the end-to-end path, CI turns red before it can merge.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.contracts import load_categories, load_places, validate
from api.main import app
from api.scheduler_stub import plan_itinerary, score_place

ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def _sample_profile() -> dict:
    return json.loads((ROOT / "fixtures" / "sample.profile.json").read_text())


def test_health_ok():
    assert client.get("/health").json() == {"status": "ok"}


def test_fixtures_validate_against_contracts():
    for place in load_places("lisbon"):
        assert validate("place", place) == [], f"{place['id']} is not a valid Place"
    assert validate("traveler-profile", _sample_profile()) == []


def test_plan_returns_a_valid_itinerary():
    body = {
        "profile": _sample_profile(),
        "destination": {"name": "Lisbon", "country": "PT", "lat": 38.72, "lon": -9.14},
        "start_date": "2026-10-01",
        "end_date": "2026-10-03",
    }
    resp = client.post("/plan", json=body)
    assert resp.status_code == 200, resp.text
    itinerary = resp.json()
    assert validate("itinerary", itinerary) == []
    assert len(itinerary["days"]) == 3
    assert any(day["items"] for day in itinerary["days"]), "expected at least one scheduled stop"


def test_plan_rejects_an_invalid_profile():
    body = {
        "profile": {"interests": {}},  # missing required fields + empty interests
        "destination": {"name": "Lisbon"},
        "start_date": "2026-10-01",
        "end_date": "2026-10-02",
    }
    resp = client.post("/plan", json=body)
    assert resp.status_code == 422


def test_scores_are_nonnegative_and_something_matches():
    category_map = load_categories()["categories"]
    profile = _sample_profile()
    scores = [score_place(p, profile, category_map) for p in load_places("lisbon")]
    assert all(s >= 0 for s in scores)
    assert max(scores) > 0


def test_single_day_trip_is_handled():
    itinerary = plan_itinerary(
        _sample_profile(),
        {"name": "Lisbon"},
        "2026-10-01",
        "2026-10-01",
    )
    assert validate("itinerary", itinerary) == []
    assert len(itinerary["days"]) == 1
