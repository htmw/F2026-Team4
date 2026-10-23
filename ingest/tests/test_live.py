"""A city with no committed data is fetched live from OpenStreetMap on the first request.

Nominatim and Overpass are faked here: the tests check what is asked for and what is
done with the answer, never the network.
"""

from __future__ import annotations

import json

import pytest
import requests
from fastapi.testclient import TestClient

from api.main import app
from ingest import catalog
from ingest.geocode import clip_bbox

PORTO = {
    "lat": "41.1494",
    "lon": "-8.6107",
    "name": "Porto",
    "display_name": "Porto, Portugal",
    "boundingbox": ["41.1383", "41.1859", "-8.6912", "-8.5526"],
    "address": {"country_code": "pt", "country": "Portugal"},
}
ELEMENTS = [
    {
        "type": "node",
        "id": 1,
        "lat": 41.1458,
        "lon": -8.6110,
        "tags": {"name": "Torre dos Clérigos", "tourism": "attraction", "historic": "tower",
                 "wikidata": "Q1", "opening_hours": "Mo-Su 09:00-19:00"},
    },
    {
        "type": "node",
        "id": 2,
        "lat": 41.1470,
        "lon": -8.6150,
        "tags": {"name": "Livraria Lello", "shop": "books", "tourism": "attraction"},
    },
    {"type": "node", "id": 3, "lat": 41.1450, "lon": -8.6120, "tags": {"amenity": "cafe"}},
]


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._payload


@pytest.fixture
def live(tmp_path, monkeypatch):
    """Live ingest on, empty committed data, fake HTTP. Returns the list of calls made."""
    calls: list[tuple[str, str]] = []
    monkeypatch.setenv("WANDERWISE_LIVE_INGEST", "1")
    monkeypatch.setattr(catalog, "CITIES_DIR", tmp_path / "cities")
    monkeypatch.setattr(catalog, "EXTRA_DIRS", [])
    monkeypatch.setattr(catalog, "LIVE_DIR", tmp_path / "live")
    monkeypatch.setattr(catalog, "CACHE_DIR", tmp_path / "cache")

    def fake_get(url, params=None, **kw):
        calls.append(("geocode", params["q"]))
        return _Resp([PORTO] if "porto" in params["q"].lower() else [])

    def fake_post(url, data=None, **kw):
        calls.append(("overpass", data["data"]))
        return _Resp({"elements": ELEMENTS})

    monkeypatch.setattr(catalog, "http_get", fake_get)
    monkeypatch.setattr(catalog, "http_post", fake_post)
    monkeypatch.setattr("ingest.overpass.time.sleep", lambda s: None)
    return calls


def test_unknown_city_is_fetched_live_and_saved(live):
    city = catalog.load_city("Porto")

    assert city.source == "live"
    assert city.destination["country"] == "PT"
    assert {p["name"] for p in city.places} == {"Torre dos Clérigos", "Livraria Lello"}
    assert (catalog.LIVE_DIR / "porto-pt" / "places.json").exists()
    overpass = [q for kind, q in live if kind == "overpass"]
    assert len(overpass) == 1, "every query group goes in one request"
    assert 'tourism"~"^(attraction' in overpass[0] and 'amenity"~"^(bar' in overpass[0]


def test_second_request_reuses_the_saved_city(live):
    catalog.load_city("Porto")
    catalog.load_city("Porto, Portugal")

    assert sum(kind == "overpass" for kind, _ in live) == 1


def test_stale_live_city_is_fetched_again(live, monkeypatch):
    catalog.load_city("Porto")
    monkeypatch.setattr(catalog, "LIVE_MAX_AGE_DAYS", 0)
    for f in (catalog.CACHE_DIR / "porto").glob("overpass_*.json"):
        f.unlink()
    catalog.load_city("Porto")

    assert sum(kind == "overpass" for kind, _ in live) == 2


def test_live_fetch_covers_the_centre_not_the_whole_admin_area():
    bbox = clip_bbox((40.0, -10.0, 43.0, -7.0), 41.15, -8.61, 6.0)

    assert bbox[2] - bbox[0] == pytest.approx(12 / 111.32)
    assert bbox[0] < 41.15 < bbox[2] and bbox[1] < -8.61 < bbox[3]


def test_a_name_openstreetmap_does_not_know_is_rejected(live):
    with pytest.raises(catalog.CityNotAvailable, match="Atlantisville"):
        catalog.load_city("Atlantisville")


def test_openstreetmap_down_is_a_fetch_failure(live, monkeypatch):
    def down(*a, **kw):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr(catalog, "http_get", down)
    with pytest.raises(catalog.CityFetchFailed, match="reach OpenStreetMap"):
        catalog.load_city("Porto")


def test_committed_cities_are_never_fetched(live, monkeypatch):
    monkeypatch.setattr(catalog, "CITIES_DIR", catalog.ROOT / "data" / "cities")

    assert catalog.load_city("Rome").source == "snapshot"
    assert catalog.load_city("Lisbon").source == "fixture"
    assert live == []


def test_plan_for_a_live_city_returns_an_itinerary(live):
    profile = json.loads((catalog.ROOT / "fixtures" / "sample.profile.json").read_text())
    body = {
        "profile": profile,
        "destination": {"name": "Porto"},
        "start_date": "2026-11-10",
        "end_date": "2026-11-10",
    }
    resp = TestClient(app).post("/plan", json=body)

    assert resp.status_code == 200, resp.text
    itinerary = resp.json()
    assert itinerary["destination"]["country"] == "PT"
    assert any("live from OpenStreetMap" in w for w in itinerary["warnings"])


def test_plan_says_503_when_openstreetmap_is_down(live, monkeypatch):
    monkeypatch.setattr(catalog, "http_get", lambda *a, **kw: _Resp([], status=503))
    profile = json.loads((catalog.ROOT / "fixtures" / "sample.profile.json").read_text())
    body = {
        "profile": profile,
        "destination": {"name": "Porto"},
        "start_date": "2026-11-10",
        "end_date": "2026-11-10",
    }
    resp = TestClient(app).post("/plan", json=body)

    assert resp.status_code == 503
