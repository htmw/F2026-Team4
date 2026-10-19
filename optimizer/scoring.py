
"""Rule-based attraction scoring for Wanderwise."""

from __future__ import annotations

from typing import Any


def matched_interests(
    place: dict[str, Any],
    category_map: dict[str, list[str]],
) -> set[str]:
    result: set[str] = set()

    for category in place.get("categories", []):
        result.update(category_map.get(category, []))

    return result


def score(
    place: dict[str, Any],
    profile: dict[str, Any],
    category_map: dict[str, list[str]] | None = None,
) -> float:
    """Return a normalized preference score from 0 to 1."""
    category_map = category_map or {}
    avoided = set(profile.get("avoid", []))

    if place["id"] in avoided:
        return 0.0

    if avoided.intersection(place.get("categories", [])):
        return 0.0

    interests = profile.get("interests", {})
    matched = matched_interests(place, category_map)

    interest_score = sum(
        float(interests.get(name, 0.0))
        for name in matched
    )

    interest_score /= max(1, len(interests))
    interest_score = min(1.0, interest_score)

    popularity = float(place.get("popularity", 0.5))
    rating = float(place.get("rating", 3.0)) / 5.0
    novelty = float(profile.get("novelty_appetite", 0.3))

    # Less popularity creates an exploration bonus.
    exploration = 1.0 - popularity

    quality = (
        0.75 * interest_score
        + 0.15 * rating
        + 0.10 * (
            (1.0 - novelty) * popularity
            + novelty * exploration
        )
    )

    return round(max(0.0, min(1.0, quality)), 4)


def recommendation_reason(
    place: dict[str, Any],
    profile: dict[str, Any],
    category_map: dict[str, list[str]],
) -> str:
    interests = matched_interests(place, category_map)
    weights = profile.get("interests", {})

    best = sorted(
        interests,
        key=lambda name: weights.get(name, 0),
        reverse=True,
    )

    if best and weights.get(best[0], 0) > 0:
        return f"Matches your interest in {best[0]}."

    return "Recommended based on location and popularity."
