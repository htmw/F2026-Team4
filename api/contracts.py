"""Load and validate against the JSON Schemas in /contracts.

Every component talks to the rest of the system through these three shapes
(Place, TravelerProfile, Itinerary). This module is the one place that knows
where the schemas live and how to check data against them.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"
FIXTURES = ROOT / "fixtures"

# Map short names -> schema file names.
_SCHEMA_FILES = {
    "place": "place.schema.json",
    "traveler-profile": "traveler-profile.schema.json",
    "itinerary": "itinerary.schema.json",
}


@cache
def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@cache
def _validator(name: str) -> Draft202012Validator:
    schema = _load_json(CONTRACTS / _SCHEMA_FILES[name])
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate(name: str, data: Any) -> list[str]:
    """Return a list of human-readable validation errors. Empty list == valid."""
    errors = sorted(_validator(name).iter_errors(data), key=lambda e: list(e.path))
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]


def load_categories() -> dict[str, Any]:
    return _load_json(CONTRACTS / "categories.json")


def load_places(city: str = "lisbon") -> list[dict[str, Any]]:
    """Load fixture places for a city. Ingest team will replace this with real data later."""
    return _load_json(FIXTURES / f"{city}.places.json")
