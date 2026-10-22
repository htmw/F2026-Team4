import pytest

from api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _body(destination):
    return {
        "destination": destination,
        "preferences": {},
    }


@pytest.mark.parametrize(
    "name",
    [
        "Lisbon",
        "Porto",
        "Tbilisi",
        "Madrid",
        "Paris",
        "Rome",
        "New York",
    ],
)
def test_supported_cities_can_be_planned(name):
    resp = client.post("/plan", json=_body({"name": name}))

    assert resp.status_code == 200


def test_a_city_without_data_is_rejected_with_a_clear_message():
    resp = client.post("/plan", json=_body({"name": "Tokyo"}))

    assert resp.status_code == 422
