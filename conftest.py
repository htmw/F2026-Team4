from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def no_live_ingest(monkeypatch):
    """No test fetches a city from OpenStreetMap unless it turns live ingest back on itself."""
    monkeypatch.setenv("WANDERWISE_LIVE_INGEST", "0")
