
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

    # Use the traveler's strongest matching interest. Summing and dividing by the
    # number of interests favoured places tagged with many categories, so a
    # traveler whose top interest is food got palaces instead of restaurants.
    interest_score = max(
        (float(interests.get(name, 0.0)) for name in matched),
        default=0.0,
    )
    interest_score = max(0.0, min(1.0, interest_score))

    # A place that matches none of the traveler's interests is not a recommendation,
    # however popular it is.
    if interest_score <= 0:
        return 0.0

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
    """Name every interest of the traveler's that this place serves, strongest first.

    Naming only the strongest one hid the rest: the Pantheon is history AND
    architecture, and a museum is art as well as history.
    """
    weights = profile.get("interests", {})
    served = sorted(
        (name for name in matched_interests(place, category_map) if weights.get(name, 0) > 0),
        key=lambda name: (-weights.get(name, 0), name),
    )[:3]

    if not served:
        return "Recommended based on location and popularity."
    if len(served) == 1:
        return f"Matches your interest in {served[0]}."
    return f"Matches your interests in {', '.join(served[:-1])} and {served[-1]}."
