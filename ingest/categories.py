"""OSM tags -> the controlled vocabulary in contracts/categories.json, plus per-category defaults.

One global mapping for every destination. It may only emit keys that exist in the
vocabulary (checked at runtime by check_against_vocabulary). Vocabulary keys that OSM
tags cannot express reliably (neighborhood, day_trip) are reported as gaps, not guessed.
"""

from __future__ import annotations

import json
from pathlib import Path

_CHURCH_BUILDINGS = {"church", "cathedral", "chapel", "basilica"}
_LANDMARK_HISTORIC = {
    "ruins",
    "archaeological_site",
    "city_gate",
    "tower",
    "manor",
    "building",
    "monastery",
    "citywalls",
    "aqueduct",
}
_SHOP_VALUES = {"mall", "department_store", "souvenir", "gift", "antiques"}

RULE_OUTPUTS = {
    "museum",
    "gallery",
    "castle",
    "palace",
    "monument",
    "church",
    "viewpoint",
    "landmark",
    "park",
    "garden",
    "beach",
    "restaurant",
    "cafe",
    "bakery",
    "market",
    "bar",
    "nightclub",
    "shop",
}


def map_categories(tags: dict) -> list[str]:
    """Return vocabulary categories for an OSM element. First entry is the primary category."""
    out: list[str] = []

    def add(c: str) -> None:
        if c not in out:
            out.append(c)

    tourism, historic = tags.get("tourism"), tags.get("historic")
    amenity, shop = tags.get("amenity"), tags.get("shop")
    building = tags.get("building")

    if tourism == "museum":
        add("museum")
    if tourism == "gallery":
        add("gallery")
    if historic in {"castle", "fort", "fortress"}:
        add("palace" if tags.get("castle_type") == "palace" or building == "palace" else "castle")
    if building == "palace":
        add("palace")
    if historic == "monument":
        add("monument")
    if amenity == "place_of_worship" and building in _CHURCH_BUILDINGS:
        add("church")
    if tourism == "viewpoint":
        add("viewpoint")
    if tourism == "attraction" or historic in _LANDMARK_HISTORIC:
        add("landmark")
    leisure = tags.get("leisure")
    if leisure == "park":
        add("park")
    if leisure == "garden":
        add("garden")
    if tags.get("natural") == "beach":
        add("beach")
    if amenity == "restaurant":
        add("restaurant")
    if amenity == "cafe":
        add("cafe")
    if shop == "bakery":
        add("bakery")
    if amenity == "marketplace":
        add("market")
    if amenity in {"bar", "pub"}:
        add("bar")
    if amenity == "nightclub":
        add("nightclub")
    if shop in _SHOP_VALUES:
        add("shop")
    return out


# --- Defaults. Always labelled `inferred`; they are guesses by category, never city data. ---
DEFAULT_DURATION_MIN = {
    "museum": 90,
    "gallery": 60,
    "monument": 20,
    "landmark": 30,
    "church": 30,
    "castle": 90,
    "palace": 90,
    "viewpoint": 20,
    "park": 60,
    "garden": 45,
    "beach": 120,
    "restaurant": 75,
    "cafe": 45,
    "bakery": 15,
    "market": 60,
    "bar": 90,
    "nightclub": 150,
    "shop": 45,
    "neighborhood": 90,
    "day_trip": 480,
}

_ALL_DAY = [("00:00", "23:59")]
DEFAULT_HOURS = {
    "museum": [("10:00", "18:00")],
    "gallery": [("10:00", "18:00")],
    "monument": _ALL_DAY,
    "landmark": _ALL_DAY,
    "viewpoint": _ALL_DAY,
    "beach": _ALL_DAY,
    "church": [("09:00", "18:00")],
    "castle": [("09:30", "18:00")],
    "palace": [("09:30", "18:00")],
    "park": [("08:00", "20:00")],
    "garden": [("08:00", "20:00")],
    "restaurant": [("12:00", "15:00"), ("19:00", "23:00")],
    "cafe": [("08:00", "19:00")],
    "bakery": [("07:00", "19:00")],
    "market": [("08:00", "14:00")],
    "shop": [("10:00", "19:00")],
    "bar": [("18:00", "23:59")],
    "nightclub": [("00:00", "04:00"), ("22:00", "23:59")],
    "neighborhood": _ALL_DAY,
    "day_trip": [("09:00", "18:00")],
}

# Categories that are usually free to enter. Others get cost confidence "unknown" when
# OSM has no fee/charge tag: we do not invent prices.
FREE_BY_DEFAULT = {
    "monument",
    "landmark",
    "church",
    "viewpoint",
    "park",
    "garden",
    "beach",
    "market",
    "shop",
    "neighborhood",
}


def load_vocabulary(path: Path) -> set[str]:
    return set(json.loads(Path(path).read_text(encoding="utf-8"))["categories"])


def check_against_vocabulary(vocab: set[str]) -> None:
    """Fail loudly if the mapping or defaults use a key the contract does not define."""
    used = set(RULE_OUTPUTS) | set(DEFAULT_DURATION_MIN) | set(DEFAULT_HOURS) | FREE_BY_DEFAULT
    missing = used - vocab
    if missing:
        raise ValueError(f"categories not in contracts/categories.json: {sorted(missing)}")
    uncovered = RULE_OUTPUTS - set(DEFAULT_DURATION_MIN)
    if uncovered | (RULE_OUTPUTS - set(DEFAULT_HOURS)):
        raise ValueError("every mapped category needs a default duration and default hours")


def unmapped_vocabulary(vocab: set[str]) -> list[str]:
    """Vocabulary keys no OSM rule can produce (reported as gaps in the build report)."""
    return sorted(vocab - RULE_OUTPUTS)
