"""Generate synthetic training data so the whole ML loop runs with zero downloads.

A ranking model learns from examples of "for this traveler, these places were a good fit
and these weren't." We don't have real users yet, so we *simulate* them: invent travelers
with hidden preferences, score every candidate place with a secret utility function
(interest match + quality + price + novelty + noise), and turn those utilities into graded
relevance labels. The model then has to *rediscover* that hidden function from the features.

This is the Sprint-1 data source. In Sprint 2 the Data team swaps this for a real public
dataset (e.g. Yelp) with the same shape: a list of "queries", each a traveler + candidate
places + relevance labels.
"""

from __future__ import annotations

import random

import numpy as np

from api.contracts import load_categories, load_places
from ranker.features import INTERESTS, extract_features, interests_touched

_CATEGORY_KEYS = list(load_categories()["categories"].keys())


def _synthetic_place(rng: random.Random, idx: int) -> dict:
    n = rng.randint(1, 3)
    return {
        "id": f"syn:{idx}",
        "name": f"Synthetic Place {idx}",
        "lat": 38.72 + rng.uniform(-0.05, 0.05),
        "lon": -9.14 + rng.uniform(-0.05, 0.05),
        "categories": rng.sample(_CATEGORY_KEYS, n),
        "typical_duration_minutes": rng.choice([30, 45, 60, 90, 120]),
        "cost": {
            "amount": round(rng.uniform(0, 40), 1),
            "currency": "EUR",
            "confidence": rng.choice(["known", "inferred", "unknown"]),
        },
        "hours": {"confidence": rng.choice(["known", "inferred", "unknown"])},
        "rating": round(rng.uniform(3.0, 5.0), 1),
        "popularity": round(rng.uniform(0.0, 1.0), 2),
        "source": "synthetic",
    }


def build_pool(rng: random.Random, n_synthetic: int = 30) -> list[dict]:
    """The candidate places: the real Lisbon fixtures plus some synthetic variety."""
    pool = list(load_places("lisbon"))
    pool.extend(_synthetic_place(rng, i) for i in range(n_synthetic))
    return pool


def _random_profile(rng: random.Random) -> dict:
    return {
        "interests": {k: round(rng.random(), 2) for k in INTERESTS},
        "pace": round(rng.random(), 2),
        "max_walk_minutes": rng.choice([10, 20, 30, 45]),
        "day_start": "09:00",
        "day_end": "22:00",
        "budget": {"total": rng.choice([300, 600, 1200, 2000]), "currency": "EUR"},
        "novelty_appetite": round(rng.random(), 2),
    }


def _true_utility(profile: dict, place: dict, rng: random.Random) -> float:
    """The hidden 'ground truth' the model must learn to approximate.

    It mixes personalization (interest match) with quality, price and novelty, plus noise,
    so no single baseline feature can trivially reproduce it.
    """
    latent = profile["interests"]
    match = sum(latent.get(i, 0.0) for i in interests_touched(place))
    rating = float(place.get("rating", 0.0)) / 5.0
    popularity = float(place.get("popularity", 0.0))
    price = float(place["cost"]["amount"])
    price_penalty = price / max(profile["budget"]["total"], 1) * 10.0
    novelty = (1.0 - popularity) * profile["novelty_appetite"]
    noise = rng.gauss(0.0, 0.15)
    return (
        1.0 * match
        + 0.6 * rating
        + 0.4 * popularity
        - 0.5 * price_penalty
        + 0.3 * novelty
        + noise
    )


def _graded_relevance(utilities: list[float]) -> list[int]:
    """Turn continuous utilities into 0..4 relevance grades by rank within the query."""
    ranks = np.argsort(np.argsort(utilities))  # 0 = worst, n-1 = best
    n = len(utilities)
    return [int(min(4, (r * 5) // n)) for r in ranks]


def make_dataset(n_travelers: int = 120, k: int = 15, seed: int = 0) -> list[dict]:
    """Build a list of ranking 'queries'.

    Each query is one traveler with k candidate places, where every candidate carries a
    relevance label (0..4) and its precomputed feature vector.
    """
    rng = random.Random(seed)
    pool = build_pool(rng)
    queries: list[dict] = []
    for _ in range(n_travelers):
        profile = _random_profile(rng)
        candidates = rng.sample(pool, min(k, len(pool)))
        utilities = [_true_utility(profile, p, rng) for p in candidates]
        grades = _graded_relevance(utilities)
        items = [
            {"place": p, "relevance": g, "features": extract_features(p, profile)}
            for p, g in zip(candidates, grades, strict=True)
        ]
        queries.append({"profile": profile, "items": items})
    return queries


def to_matrix(queries: list[dict]) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Flatten queries into (X, y, group) — the shape LightGBM's ranker wants.

    `group` tells LightGBM how many rows belong to each query, so it ranks within a query
    rather than across all travelers at once.
    """
    features: list[list[float]] = []
    labels: list[int] = []
    group: list[int] = []
    for q in queries:
        group.append(len(q["items"]))
        for item in q["items"]:
            features.append(item["features"])
            labels.append(item["relevance"])
    return np.array(features, dtype=float), np.array(labels, dtype=int), group
