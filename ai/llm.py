"""Provider-agnostic access to a language model.

Everything outside /ai talks to an `LLM` and never to a provider directly, so swapping the
local model for a hosted one means adding a class here and changing configuration, not
rewriting callers.

Configuration (environment variables):
    WANDERWISE_LLM_PROVIDER   "ollama" (the only provider so far)
    WANDERWISE_LLM_MODEL      model name, default "llama3"
    WANDERWISE_OLLAMA_URL     default "http://localhost:11434"
"""

from __future__ import annotations

import os
from typing import Any, Protocol

import requests

DEFAULT_MODEL = "llama3"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
REQUEST_TIMEOUT = 120  # seconds; the first call also loads the model into memory


class LLMError(RuntimeError):
    """The model was reached but the call failed."""


class LLMUnavailable(LLMError):
    """The model can't be reached at all (server down, model not installed)."""


class LLM(Protocol):
    def chat(self, messages: list[dict[str, str]], schema: dict[str, Any] | None = None) -> str:
        """Send a conversation and return the reply text.

        `messages` are {"role": "system" | "user" | "assistant", "content": str}.
        `schema`, when given, is a JSON Schema the reply must follow; providers that support
        structured output enforce it while generating.
        """
        ...


class OllamaLLM:
    """A model served by a local Ollama server (https://ollama.com)."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_OLLAMA_URL,
        *,
        timeout: float = REQUEST_TIMEOUT,
        post=requests.post,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._post = post

    def chat(self, messages: list[dict[str, str]], schema: dict[str, Any] | None = None) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": schema if schema is not None else "json",
            # Extraction should be repeatable, not creative.
            "options": {"temperature": 0},
        }
        try:
            resp = self._post(f"{self.base_url}/api/chat", json=body, timeout=self.timeout)
        except requests.ConnectionError as exc:
            raise LLMUnavailable(
                f"Can't reach Ollama at {self.base_url}. Is it running (`ollama serve`)?"
            ) from exc
        except requests.Timeout as exc:
            raise LLMError(f"Ollama took longer than {self.timeout}s to answer.") from exc

        if resp.status_code == 404:
            raise LLMUnavailable(
                f"Ollama has no model named {self.model!r}. Run `ollama pull {self.model}`."
            )
        if resp.status_code != 200:
            raise LLMError(f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            return resp.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMError(f"Unexpected response from Ollama: {resp.text[:200]}") from exc


def get_llm() -> LLM:
    """The configured model. Used by the API as a FastAPI dependency."""
    provider = os.environ.get("WANDERWISE_LLM_PROVIDER", "ollama")
    if provider == "ollama":
        return OllamaLLM(
            model=os.environ.get("WANDERWISE_LLM_MODEL", DEFAULT_MODEL),
            base_url=os.environ.get("WANDERWISE_OLLAMA_URL", DEFAULT_OLLAMA_URL),
        )
    raise LLMUnavailable(f"Unknown LLM provider {provider!r}. Supported: ollama.")
