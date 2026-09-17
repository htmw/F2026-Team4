"""Turn a (place, traveler) pair into a list of numbers the model can learn from.

A machine-learning model can't read a Place dict — it needs a fixed-length list of
numbers (a "feature vector"). This module is the single place that defines those numbers,
so training and serving always compute them the same way. The features are all
*content-based* (they describe the match between a place and a traveler, not the place's
identity), which is what lets a model trained on one city work on another.
"""

from __future__ import annotations

from api.contracts import load_categories

_CATS = load_categories()
INTERESTS: list[str] = list(_CATS["interests"])
_CATEGORY_MAP: dict[str, list[str]] = _CATS["categories"]

# The order here is the contract between training and serving. Never reorder without
# retraining, and keep this list in sync with extract_features() below.
FEATURE_NAMES: list[str] = [
    "interest_match_sum",   # how strongly the traveler's interests overlap this place
    "interest_match_avg",   # same, averaged over the interests the place touches
    "popularity",           # 0..1 how popular the place is
    "rating_norm",          # rating / 5
    "price",                # ticket/cost amount
    "price_fits_budget",    # 1 if cheap relative to budget, else 0
    "duration_norm",        # typical visit length / 240 min
    "hours_known",          # 1 if opening hours are verified data
    "cost_known",           # 1 if the price is verified data
    "num_categories",       # how many category tags the place has
    "novelty",             # (1 - popularity) * the traveler's appetite for novelty
]


def feature_names() -> list[str]:
    return list(FEATURE_NAMES)


def interests_touched(place: dict) -> set[str]:
    """The set of interest dimensions this place speaks to, via its categories."""
    touched: set[str] = set()
    for category in place.get("categories", []):
        touched.update(_CATEGORY_MAP.get(category, []))
    return touched


def extract_features(place: dict, profile: dict, context: dict | None = None) -> list[float]:
    """Compute the feature vector for one (place, traveler) pair.

    Returns a list of floats in the exact order of FEATURE_NAMES.
    `context` (weather, time-of-day) is accepted for forward-compatibility; the current
    feature set does not use it yet.
    """
    interests = interests_touched(place)
    weights = profile.get("interests", {})
    match_sum = float(sum(weights.get(i, 0.0) for i in interests))
    match_avg = match_sum / len(interests) if interests else 0.0

    popularity = float(place.get("popularity", 0.0))
    rating_norm = float(place.get("rating", 0.0)) / 5.0
    price = float(place["cost"]["amount"])
    budget = float(profile.get("budget", {}).get("total", 0.0)) or 1.0
    price_fits_budget = 1.0 if price <= 0.10 * budget else 0.0
    duration_norm = float(place.get("typical_duration_minutes", 0)) / 240.0
    hours_known = 1.0 if place.get("hours", {}).get("confidence") == "known" else 0.0
    cost_known = 1.0 if place.get("cost", {}).get("confidence") == "known" else 0.0
    num_categories = float(len(place.get("categories", [])))
    novelty = (1.0 - popularity) * float(profile.get("novelty_appetite", 0.0))

    return [
        match_sum,
        match_avg,
        popularity,
        rating_norm,
        price,
        price_fits_budget,
        duration_norm,
        hours_known,
        cost_known,
        num_categories,
        novelty,
    ]
