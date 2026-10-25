"""Prepare ranking examples from real OSM places.

Places are real. Travelers and suitability grades are simulated.
Missing ratings stay absent; the existing feature code encodes them as 0.
"""

from __future__ import annotations

import argparse
import hashlib
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
    if n_travelers < 2:
        raise ValueError("At least two traveler examples are required.")

    if k < 1:
        raise ValueError("Candidates per traveler must be at least 1.")

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
    """Keep each traveler in the same split across every city.

    Approximately 80% of profiles go to training and 20% to testing.
    Use the same split seed for every city.
    """
    if len(queries) < 2:
        raise ValueError("At least two traveler examples are required.")

    train = []
    test = []

    for query in queries:
        profile_text = json.dumps(
            query["profile"],
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

        # Identical profiles always receive the same assignment,
        # regardless of their city or position in the dataset.
        key = f"{seed}:{profile_text}".encode("utf-8")
        digest = hashlib.sha256(key).digest()
        bucket = int.from_bytes(digest[:8], "big") % 100

        if bucket < 20:
            test.append(query)
        else:
            train.append(query)

    if not train or not test:
        raise ValueError(
            "The split produced an empty training or testing set. "
            "Generate more traveler examples."
        )

    return train, test


def save_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--city",
        default="rome",
        help="City folder name, for example rome. Default: rome.",
    )
    parser.add_argument(
        "--places",
        type=Path,
        default=None,
        help="Optional path to the selected city's places.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output folder for the generated datasets.",
    )

    args = parser.parse_args()

    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-_"

    if not args.city or any(char not in allowed for char in args.city):
        parser.error(
            "--city must use lowercase letters, numbers, "
            "hyphens or underscores."
        )

    if args.places is None:
        args.places = (
            ROOT / "data" / "cities" / args.city / "places.json"
        )

    if args.output is None:
        args.output = ROOT / "data" / "training" / args.city

    if not args.places.is_file():
        parser.error(
            f"Places file not found: {args.places}. "
            "Provide the city's collected data first, "
            "or specify its file using --places."
        )

    queries = make_dataset(args.places)
    train, test = split_dataset(queries)

    args.output.mkdir(parents=True, exist_ok=True)

    save_json(args.output / "train.json", train)
    save_json(args.output / "test.json", test)

    places = json.loads(args.places.read_text(encoding="utf-8"))
    rated = sum(place.get("rating") is not None for place in places)

    summary = {
        "city": args.city,
        "seed": 42,
        "source_file": str(args.places),
        "source_places": len(places),
        "places_with_ratings": rated,
        "train_travelers": len(train),
        "test_travelers": len(test),
        "candidates_per_traveler": 15,
        "feature_names": feature_names(),
        "split_method": (
            "SHA-256 of the traveler profile and split seed; "
            "approximately 80% training and 20% testing."
        ),
        "cross_city_split": (
            "Identical traveler profiles stay in the same split "
            "across cities when the same split seed is used."
        ),
        "place_data": (
            "Real OSM records; existing curated details are "
            "preserved when present."
        ),
        "traveler_profiles": "Simulated.",
        "suitability_grades": (
            "Calculated using the existing synthetic formula."
        ),
        "missing_ratings": (
            "Absent in records; existing features encode as 0."
        ),
        "limitations": [
            "Grades are not judgments from real travelers.",
            "The same places may appear for different travelers in both sets.",
            "This split tests unseen travelers, not unseen places or cities.",
            "Existing cost and popularity estimates are preserved.",
            (
                "The city label is supplied by the caller; geographic "
                "location and currency compatibility are not validated "
                "by this script."
            ),
        ],
    }

    save_json(args.output / "summary.json", summary)

    print(f"City: {args.city}")
    print(f"Training travelers: {len(train)}")
    print(f"Testing travelers: {len(test)}")
    print("Split: approximately 80% training and 20% testing.")
    print(f"Files saved to: {args.output}")
    print("Model training has not been run.")


if __name__ == "__main__":
    main()