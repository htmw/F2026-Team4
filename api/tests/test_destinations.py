"""The API plans from the city the traveler asked for, or says it has no data for it.

Sprint 1 integration testing found that asking for New York returned Lisbon places. These
tests pin the fixed behaviour: the requested city's data, or a clear 422.
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


def test_unknown_city_is_rejected_with_a_clear_message():
    resp = client.post("/plan", json=_body({"name": "New York"}))

    assert resp.status_code == 422
    message = resp.json()["detail"]["destination_errors"][0]
    assert "New York" in message
    assert "Rome" in message


@pytest.mark.parametrize("destination", [{}, {"name": ""}, {"name": "Rome, Georgia"}])
def test_missing_or_wrong_city_is_not_planned_in_lisbon(destination):
    resp = client.post("/plan", json=_body(destination))

    assert resp.status_code == 422
    assert "Cities with data" in resp.json()["detail"]["destination_errors"][0]


def test_rome_is_planned_from_the_rome_snapshot():
    rome_ids = {p["id"] for p in catalog.load_places("Rome")}
    resp = client.post("/plan", json=_body({"name": "Rome"}))

    assert resp.status_code == 200, resp.text
    itinerary = resp.json()
    assert validate("itinerary", itinerary) == []
    scheduled = _scheduled_ids(itinerary)
    assert scheduled, "expected at least one stop"
    assert set(scheduled) <= rome_ids
    assert itinerary["destination"]["country"] == "IT"
    assert itinerary["destination"]["lat"] == pytest.approx(41.89, abs=0.1)


def test_city_and_country_form_is_accepted():
    resp = client.post("/plan", json=_body({"name": "Rome, Italy"}))

    assert resp.status_code == 200, resp.text


def test_destination_sent_as_city_key_still_works():
    resp = client.post("/plan", json=_body({"city": "Lisbon"}))

    assert resp.status_code == 200, resp.text
    assert all(pid.startswith("fixture:") for pid in _scheduled_ids(resp.json()))


def test_fixture_city_warns_that_it_is_sample_data():
    resp = client.post("/plan", json=_body({"name": "Lisbon"}))

    assert any("sample file" in w for w in resp.json()["warnings"])
