
from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def _body(destination):
    return {
        "destination": destination,
        "preferences": {},
    }


def test_a_city_without_data_is_rejected_with_a_clear_message():
    resp = client.post("/plan", json=_body({"name": "Tokyo"}))

    assert resp.status_code == 422
