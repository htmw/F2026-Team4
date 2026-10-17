"""Trip state: every planned trip is saved so it can be fetched and re-planned later.

SQLite from the standard library, one row per trip. The original request is stored
next to the itinerary because re-planning needs the profile, destination and dates the
trip was built from.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    trip_id    TEXT PRIMARY KEY,
    request    TEXT NOT NULL,
    itinerary  TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class TripStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        # A fresh connection per call: FastAPI runs sync endpoints on a thread pool, and a
        # sqlite3 connection can't be shared across threads.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute(_SCHEMA)
        return conn

    def save(self, trip_id: str, request: dict[str, Any], itinerary: dict[str, Any]) -> None:
        """Insert the trip, or overwrite it if it already exists (re-planning)."""
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO trips (trip_id, request, itinerary, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        trip_id,
                        json.dumps(request),
                        json.dumps(itinerary),
                        datetime.now(UTC).isoformat(timespec="seconds"),
                    ),
                )

    def get(self, trip_id: str) -> dict[str, Any] | None:
        """Return {"request": ..., "itinerary": ...}, or None if there is no such trip."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT request, itinerary FROM trips WHERE trip_id = ?", (trip_id,)
            ).fetchone()
        if row is None:
            return None
        return {"request": json.loads(row[0]), "itinerary": json.loads(row[1])}
