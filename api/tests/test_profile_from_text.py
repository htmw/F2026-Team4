"""Tests for POST /profile/from-text, with a fake model in place of Ollama."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ai import LLMUnavailable, get_llm
from ai.tests.fakes import FakeLLM, reply
from api.contracts import validate
from api.main import app

client = TestClient(app)


@pytest.fixture
def use_llm():
    """Install a fake model for one test: use_llm(FakeLLM(...))."""

    def install(llm):
        app.dependency_overrides[get_llm] = lambda: llm

    yield install
    app.dependency_overrides.pop(get_llm, None)


def test_returns_a_valid_profile_and_the_defaulted_fields(use_llm):
    use_llm(FakeLLM(reply(pace=0.2, budget_total=900, budget_currency="GBP")))
    resp = client.post("/profile/from-text", json={"text": "Slow trip, about 900 pounds."})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert validate("traveler-profile", body["profile"]) == []
    assert body["profile"]["budget"] == {"total": 900, "currency": "GBP"}
    assert body["defaults_used"] == ["max_walk_minutes", "day_start", "day_end"]


def test_the_profile_can_be_planned_with(use_llm):
    use_llm(FakeLLM(reply()))
    profile = client.post("/profile/from-text", json={"text": "Anything."}).json()["profile"]

    resp = client.post(
        "/plan",
        json={
            "profile": profile,
            "destination": {"name": "Lisbon"},
            "start_date": "2026-11-10",
            "end_date": "2026-11-11",
        },
    )
    assert resp.status_code == 200, resp.text


def test_empty_text_is_422(use_llm):
    use_llm(FakeLLM())
    assert client.post("/profile/from-text", json={"text": "   "}).status_code == 422


def test_very_long_text_is_422(use_llm):
    use_llm(FakeLLM())
    resp = client.post("/profile/from-text", json={"text": "x" * 2001})
    assert resp.status_code == 422


def test_model_unavailable_is_503(use_llm):
    class DownLLM:
        def chat(self, messages, schema=None):
            raise LLMUnavailable("Can't reach Ollama.")

    use_llm(DownLLM())
    resp = client.post("/profile/from-text", json={"text": "Food trip."})
    assert resp.status_code == 503
    assert "Ollama" in resp.json()["detail"]


def test_model_that_never_gives_a_valid_profile_is_502(use_llm):
    use_llm(FakeLLM("bad", "bad", "bad"))
    resp = client.post("/profile/from-text", json={"text": "Food trip."})
    assert resp.status_code == 502
