"""Cities with no committed data are fetched live from OpenStreetMap (faked here)."""

from __future__ import annotations

import json

import pytest
import requests
from fastapi.testclient import TestClient

from api.main import app
from ingest import catalog
from ingest.overpass import LIVE_TIMEOUT

PORTO = {
    "name": "Porto",
    "display_name": "Porto, Portugal",
    "addresstype": "city",
    "lat": "41.1494",
    "lon": "-8.6107",
    "boundingbox": ["41.1383", "41.1859", "-8.6912", "-8.5526"],
    "address": {"country_code": "pt", "country": "Portugal"},
}
PORTUGAL = {**PORTO, "name": "Portugal", "addresstype": "country"}
TOWER = {
    "type": "node",
    "id": 1,
    "lat": 41.1458,
    "lon": -8.6110,
    "tags": {"name": "Torre dos Clérigos", "tourism": "attraction"},
}


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self.payload


@pytest.fixture
def osm(tmp_path, monkeypatch):
    """Live fetching on, with a fake OpenStreetMap. Returns the Overpass queries sent."""
    queries = []
    monkeypatch.setenv("WANDERWISE_LIVE_INGEST", "1")
    monkeypatch.setattr(catalog, "LIVE_DIR", tmp_path / "live")
    monkeypatch.setattr(catalog, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr("ingest.overpass.time.sleep", lambda s: None)

    def nominatim(url, params, **kw):
        assert params["featureType"] == "settlement", "never a shop or a hotel"
        found = {"porto": [PORTO], "portugal": [PORTUGAL]}
        return FakeResponse(found.get(params["q"].lower(), []))

    def overpass(url, data, **kw):
        queries.append(data["data"])
        return FakeResponse({"elements": [TOWER]})

    monkeypatch.setattr(catalog, "http_get", nominatim)
    monkeypatch.setattr(catalog, "http_post", overpass)
    return queries


def plan(city):
    profile = json.loads((catalog.ROOT / "fixtures" / "sample.profile.json").read_text())
    body = {"profile": profile, "destination": {"name": city},
            "start_date": "2026-11-10", "end_date": "2026-11-10"}
    return TestClient(app).post("/plan", json=body)


def test_new_city_is_fetched_once_and_kept(osm):
    city = catalog.load_city("Porto")
    catalog.load_city("Porto")

    assert city.source == "live"
    assert city.destination["country"] == "PT"
    assert [p["name"] for p in city.places] == ["Torre dos Clérigos"]
    assert len(osm) == 1, "one Overpass query, and the second request reads the saved folder"


def test_plan_for_a_live_city(osm):
    resp = plan("Porto")

    assert resp.status_code == 200, resp.text
    assert resp.json()["days"][0]["items"][0]["name"] == "Torre dos Clérigos"


def test_a_live_city_is_shown_with_its_own_name_and_currency(osm, monkeypatch):
    india = {**PORTO, "name": "Karimnagar", "address": {"country_code": "in", "country": "India"}}
    monkeypatch.setattr(catalog, "http_get", lambda *a, **kw: FakeResponse([india]))
    itinerary = plan("karimnagar").json()

    assert itinerary["destination"]["name"] == "Karimnagar, India"
    assert itinerary["totals"]["currency"] == "INR"


def test_a_country_is_not_a_city(osm):
    with pytest.raises(catalog.CityNotAvailable, match="country, not a city"):
        catalog.load_city("Portugal")


def test_a_name_openstreetmap_does_not_know(osm):
    assert plan("Atlantisville").status_code == 422


def test_openstreetmap_down_is_a_503(osm, monkeypatch):
    monkeypatch.setattr(catalog, "http_get", lambda *a, **kw: FakeResponse([], status=503))

    assert plan("Porto").status_code == 503


def test_rome_and_lisbon_are_never_fetched(osm):
    assert catalog.load_city("Rome").source == "snapshot"
    assert catalog.load_city("Lisbon").source == "fixture"
    assert osm == []


def test_a_hanging_server_does_not_keep_the_traveler_waiting(osm, monkeypatch):
    timeouts = []

    def hangs(url, data, timeout, **kw):
        timeouts.append(timeout)
        raise requests.Timeout("no answer")

    monkeypatch.setattr(catalog, "http_post", hangs)

    assert plan("Porto").status_code == 503
    assert timeouts == [LIVE_TIMEOUT] * 4, "two servers, two rounds, then a clear 503"
