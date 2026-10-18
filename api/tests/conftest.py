from __future__ import annotations

import pytest

from api import main
from api.trips import TripStore


@pytest.fixture(autouse=True)
def temp_trip_store(tmp_path, monkeypatch):
    """Give every test its own empty trip database instead of data/wanderwise.db."""
    monkeypatch.setattr(main, "store", TripStore(tmp_path / "trips.db"))
