"""Tests for the Ollama provider and provider selection, with a fake HTTP layer."""

from __future__ import annotations

import pytest
import requests

from ai.llm import LLMError, LLMUnavailable, OllamaLLM, get_llm


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no JSON")
        return self._payload


def _ok(content='{"a": 1}'):
    return FakeResponse(payload={"message": {"role": "assistant", "content": content}})


def test_sends_a_chat_request_with_the_schema():
    sent = {}

    def post(url, *, json, timeout):
        sent.update(url=url, body=json, timeout=timeout)
        return _ok()

    llm = OllamaLLM("llama3", "http://ollama:11434/", post=post)
    out = llm.chat([{"role": "user", "content": "hi"}], schema={"type": "object"})

    assert out == '{"a": 1}'
    assert sent["url"] == "http://ollama:11434/api/chat"
    assert sent["body"]["model"] == "llama3"
    assert sent["body"]["format"] == {"type": "object"}
    assert sent["body"]["stream"] is False
    assert sent["body"]["options"]["temperature"] == 0


def test_asks_for_plain_json_without_a_schema():
    sent = {}

    def post(url, *, json, timeout):
        sent["body"] = json
        return _ok()

    OllamaLLM(post=post).chat([{"role": "user", "content": "hi"}])
    assert sent["body"]["format"] == "json"


def test_server_down_is_unavailable():
    def post(*args, **kwargs):
        raise requests.ConnectionError("refused")

    with pytest.raises(LLMUnavailable, match="ollama serve"):
        OllamaLLM(post=post).chat([])


def test_missing_model_is_unavailable():
    llm = OllamaLLM("llama3", post=lambda *a, **k: FakeResponse(404, text="model not found"))
    with pytest.raises(LLMUnavailable, match="ollama pull llama3"):
        llm.chat([])


def test_server_error_is_an_llm_error_but_not_unavailable():
    llm = OllamaLLM(post=lambda *a, **k: FakeResponse(500, text="boom"))
    with pytest.raises(LLMError) as err:
        llm.chat([])
    assert not isinstance(err.value, LLMUnavailable)


def test_timeout_is_an_llm_error():
    def post(*args, **kwargs):
        raise requests.Timeout("slow")

    with pytest.raises(LLMError, match="longer than"):
        OllamaLLM(post=post).chat([])


def test_unexpected_body_is_an_llm_error():
    llm = OllamaLLM(post=lambda *a, **k: FakeResponse(200, payload={"oops": True}))
    with pytest.raises(LLMError, match="Unexpected response"):
        llm.chat([])


def test_get_llm_reads_the_environment(monkeypatch):
    monkeypatch.setenv("WANDERWISE_LLM_MODEL", "phi3")
    monkeypatch.setenv("WANDERWISE_OLLAMA_URL", "http://gpu-box:11434")
    llm = get_llm()
    assert isinstance(llm, OllamaLLM)
    assert (llm.model, llm.base_url) == ("phi3", "http://gpu-box:11434")


def test_get_llm_rejects_an_unknown_provider(monkeypatch):
    monkeypatch.setenv("WANDERWISE_LLM_PROVIDER", "mystery")
    with pytest.raises(LLMUnavailable, match="Unknown LLM provider"):
        get_llm()
