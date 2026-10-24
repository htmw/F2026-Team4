"""Prepare ranking examples from real OSM places.

Places are real. Travelers and suitability grades are simulated.
Missing ratings stay absent; the existing feature code encodes them as 0.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from ranker.features import extract_features, feature_names
from ranker.synthetic import (
    _graded_relevance,
    _random_profile,
    _true_utility,
)

ROOT = Path(__file__).resolve().parent.parent


def make_dataset(
    places_path: Path,
    n_travelers: int = 500,
    k: int = 15,
    seed: int = 42,
) -> list[dict]:
    """Use the same query format as ranker.synthetic.make_dataset."""
    places = json.loads(places_path.read_text(encoding="utf-8"))

    if not isinstance(places, list) or len(places) < k:
        raise ValueError(f"Expected a list containing at least {k} places.")

    ids = [place["id"] for place in places]
    if len(ids) != len(set(ids)):
        raise ValueError("The places file contains duplicate IDs.")

    if any(str(place_id).startswith("syn:") for place_id in ids):
        raise ValueError("Synthetic places are not allowed.")

    rng = random.Random(seed)
    queries = []

    for _ in range(n_travelers):
        profile = _random_profile(rng)
        candidates = rng.sample(places, k)
        utilities = [
            _true_utility(profile, place, rng)
            for place in candidates
        ]
        grades = _graded_relevance(utilities)

        items = [
            {
                "place": place,
                "relevance": grade,
                "features": extract_features(place, profile),
            }
            for place, grade in zip(candidates, grades, strict=True)
        ]

        for item in items:
            if len(item["features"]) != len(feature_names()):
                raise ValueError("Unexpected feature-vector length.")

        queries.append({"profile": profile, "items": items})

    return queries


def split_dataset(
    queries: list[dict],
    seed: int = 42,
) -> tuple[list[dict], list[dict]]:
    """Split whole travelers, keeping their candidate places together."""
    if len(queries) < 2:
        raise ValueError("At least two traveler examples are required.")

    shuffled = list(queries)
    random.Random(seed).shuffle(shuffled)

    test_count = max(1, round(len(shuffled) * 0.20))
    train = shuffled[test_count:]
    test = shuffled[:test_count]

    def profile_key(query: dict) -> str:
        return json.dumps(query["profile"], sort_keys=True)

    train_profiles = {profile_key(query) for query in train}
    test_profiles = {profile_key(query) for query in test}

    if train_profiles & test_profiles:
        raise ValueError("A traveler profile appears in both sets.")

    return train, test


def save_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--places",
        type=Path,
        default=ROOT / "data" / "cities" / "rome" / "places.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "training" / "rome",
    )
    args = parser.parse_args()

    queries = make_dataset(args.places)
    train, test = split_dataset(queries)

    args.output.mkdir(parents=True, exist_ok=True)
    save_json(args.output / "train.json", train)
    save_json(args.output / "test.json", test)

    places = json.loads(args.places.read_text(encoding="utf-8"))
    rated = sum(place.get("rating") is not None for place in places)

    summary = {
        "city": "rome",
        "seed": 42,
        "source_file": str(args.places),
        "source_places": len(places),
        "places_with_ratings": rated,
        "train_travelers": len(train),
        "test_travelers": len(test),
        "candidates_per_traveler": 15,
        "feature_names": feature_names(),
        "place_data": "Real OSM records, including existing curated details.",
        "traveler_profiles": "Simulated.",
        "suitability_grades": "Calculated using the existing synthetic formula.",
        "missing_ratings": "Absent in records; existing features encode as 0.",
        "limitations": [
            "Grades are not judgments from real travelers.",
            "The same places may appear for different travelers in both sets.",
            "This split tests unseen travelers, not unseen places or cities.",
            "Existing cost and popularity estimates are preserved.",
        ],
    }
    save_json(args.output / "summary.json", summary)

    print(f"Training travelers: {len(train)}")
    print(f"Testing travelers: {len(test)}")
    print(f"Files saved to: {args.output}")
    print("Model training has not been run.")


if __name__ == "__main__":
    main()