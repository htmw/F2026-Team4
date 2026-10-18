"""The API plans Lisbon from the Lisbon data and refuses every other city with a clear 422.

A trip must never be planned in a different city from the one the traveler asked for.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.contracts import validate
from api.main import app
from ingest import catalog

ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def _profile() -> dict:
    return json.loads((ROOT / "fixtures" / "sample.profile.json").read_text())


def _body(destination: dict) -> dict:
    return {
        "profile": _profile(),
        "destination": destination,
        "start_date": "2026-11-10",
        "end_date": "2026-11-11",
    }


def _scheduled_ids(itinerary: dict) -> list[str]:
    return [item["place_id"] for day in itinerary["days"] for item in day["items"]]


@pytest.mark.parametrize("name", ["New York", "Rome"])
def test_a_city_without_data_is_rejected_with_a_clear_message(name):
    resp = client.post("/plan", json=_body({"name": name}))

    assert resp.status_code == 422
    message = resp.json()["detail"]["destination_errors"][0]
    assert name in message
    assert "Lisbon" in message


@pytest.mark.parametrize("destination", [{}, {"name": ""}, {"name": "Lisbon, Ohio"}])
def test_missing_or_wrong_city_is_rejected(destination):
    resp = client.post("/plan", json=_body(destination))

    assert resp.status_code == 422
    assert "Cities with data" in resp.json()["detail"]["destination_errors"][0]


def test_lisbon_is_planned_from_the_lisbon_snapshot():
    lisbon_ids = {p["id"] for p in catalog.load_places("Lisbon")}
    resp = client.post("/plan", json=_body({"name": "Lisbon"}))

    assert resp.status_code == 200, resp.text
    itinerary = resp.json()
    assert validate("itinerary", itinerary) == []
    scheduled = _scheduled_ids(itinerary)
    assert scheduled, "expected at least one stop"
    assert set(scheduled) <= lisbon_ids
    assert all(pid.startswith("osm:") for pid in scheduled)
    assert itinerary["destination"]["country"] == "PT"
    assert itinerary["destination"]["lat"] == pytest.approx(38.72, abs=0.1)


@pytest.mark.parametrize("name", ["Lisbon, Portugal", "Lisboa"])
def test_other_names_for_lisbon_are_accepted(name):
    resp = client.post("/plan", json=_body({"name": name}))

    assert resp.status_code == 200, resp.text
    assert resp.json()["destination"]["country"] == "PT"


def test_destination_sent_as_city_key_still_works():
    resp = client.post("/plan", json=_body({"city": "Lisbon"}))

    assert resp.status_code == 200, resp.text
    assert all(pid.startswith("osm:") for pid in _scheduled_ids(resp.json()))
