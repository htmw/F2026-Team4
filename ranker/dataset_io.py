"""Compact ranking-data storage without changing model features."""

from __future__ import annotations

import json
import math
from pathlib import Path

FORMAT = "wanderwise-ranking-v2"
LEGACY_FORMAT = "wanderwise-ranking-v1"


def compact_place(place: dict) -> dict:
    """Keep fields read by the current feature and label functions."""
    result = {
        "id": place["id"],
        "categories": place["categories"],
        "typical_duration_minutes": place.get(
            "typical_duration_minutes", 0
        ),
        "cost": place["cost"],
        "hours": {
            "confidence": place.get("hours", {}).get(
                "confidence", "unknown"
            )
        },
    }

    # Preserve existing values; do not invent ratings or popularity.
    for field in ("name", "rating", "popularity"):
        if field in place:
            result[field] = place[field]

    return result


def _features_match(first, second) -> bool:
    """Accept only finite feature values with tiny rounding differences."""
    if len(first) != len(second):
        return False

    return all(
        math.isfinite(left)
        and math.isfinite(right)
        and math.isclose(
            left,
            right,
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
        for left, right in zip(first, second, strict=True)
    )


def _encode(value) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def save_dataset(path: Path, queries: list[dict]) -> None:
    """Store model-relevant place fields once per dataset file."""
    from ranker.features import extract_features, feature_names

    places = {}
    stored_queries = []

    for query in queries:
        profile = query["profile"]
        items = []

        for item in query["items"]:
            original = item["place"]
            place_id = original["id"]

            if not isinstance(place_id, str) or not place_id:
                raise ValueError(
                    "Each place needs a nonempty string ID."
                )

            place = compact_place(original)

            if place_id in places and places[place_id] != place:
                raise ValueError(
                    f"Conflicting model details for place: {place_id}"
                )

            original_features = extract_features(original, profile)
            compact_features = extract_features(place, profile)

            if not _features_match(
                original_features, compact_features
            ):
                raise ValueError(
                    f"Compaction changes model features: {place_id}"
                )

            if "features" in item and not _features_match(
                item["features"], original_features
            ):
                raise ValueError(
                    f"Stored features do not match current code: {place_id}"
                )

            grade = item["relevance"]
            if type(grade) is not int or not 0 <= grade <= 4:
                raise ValueError(
                    "Relevance must be an integer from 0 to 4."
                )

            places[place_id] = place
            items.append({
                "place_id": place_id,
                "relevance": grade,
            })

        stored_queries.append({
            "profile": profile,
            "items": items,
        })

    payload = {
        "format": FORMAT,
        "feature_names": feature_names(),
        "places": places,
        "queries": stored_queries,
    }

    # Validate serialization before creating or replacing the file.
    content = _encode(payload)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_dataset(path: Path) -> list[dict]:
    """Restore the query shape used by existing model functions."""
    from ranker.features import extract_features, feature_names

    payload = json.loads(
        Path(path).read_text(encoding="utf-8")
    )

    # Earlier expanded datasets remain supported.
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        raise ValueError("Expected a dataset object or query list.")

    version = payload.get("format")
    if version not in {FORMAT, LEGACY_FORMAT}:
        raise ValueError("Unsupported ranking dataset format.")

    if (
        version == FORMAT
        and payload.get("feature_names") != feature_names()
    ):
        raise ValueError(
            "Dataset feature names differ from the current model code."
        )

    places = payload.get("places")
    queries = payload.get("queries")

    if not isinstance(places, dict) or not isinstance(queries, list):
        raise ValueError("Dataset must contain places and queries.")

    for place_id, place in places.items():
        if not isinstance(place, dict) or place.get("id") != place_id:
            raise ValueError(
                f"Place record does not match its ID: {place_id}"
            )

    restored = []

    for query in queries:
        profile = query["profile"]
        items = []

        for item in query["items"]:
            place_id = item["place_id"]

            if place_id not in places:
                raise ValueError(
                    f"Query references a missing place: {place_id}"
                )

            place = places[place_id]

            if version == LEGACY_FORMAT:
                features = item["features"]
            else:
                features = extract_features(place, profile)

            items.append({
                "place": place,
                "relevance": item["relevance"],
                "features": features,
            })

        restored.append({
            "profile": profile,
            "items": items,
        })

    return restored