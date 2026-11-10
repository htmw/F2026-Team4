"""A scripted stand-in for a language model, so tests never need Ollama."""

from __future__ import annotations

import json
from typing import Any

INTERESTS = ["food", "history", "art", "architecture", "nature", "nightlife", "shopping"]


def reply(**overrides: Any) -> str:
    """A valid model reply where nothing was mentioned, with `overrides` applied."""
    body: dict[str, Any] = {
        "interests": {name: 0.5 for name in INTERESTS},
        "pace": None,
        "max_walk_minutes": None,
        "day_start": None,
        "day_end": None,
        "budget_total": None,
        "budget_currency": None,
        "dietary": [],
        "accessibility": [],
        "avoid": [],
    }
    body.update(overrides)
    return json.dumps(body)


class FakeLLM:
    """Returns the scripted replies in order and records every call."""

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages, schema=None) -> str:
        self.calls.append({"messages": [dict(m) for m in messages], "schema": schema})
        return self.replies.pop(0)
