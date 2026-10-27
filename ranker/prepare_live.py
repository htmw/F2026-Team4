"""Fetch city data when needed and prepare compact ranking examples.

Places are real. Travelers and relevance grades are simulated.
Model training is a separate step.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from pathlib import Path

from ingest.pipeline import run_city
from ranker.dataset_io import save_dataset
from ranker.features import extract_features, feature_names
from ranker.real_data import save_json, split_dataset
from ranker.synthetic import (
    _graded_relevance,
    _random_profile,
    _true_utility,
)

ROOT = Path(__file__).resolve().parent.parent
TEST_ONLY_CITIES = {"tokyo", "bogota", "hyderabad"}


def city_words(value: str) -> set[str]:
    """Recognize reserved city names in slugs and destination names."""
    import unicodedata

    text = unicodedata.normalize("NFKD", value)
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return set(re.findall(r"[a-z]+", text))


def is_test_city(slug: str, query: str, metadata: dict) -> bool:
    words = city_words(
        " ".join([
            slug,
            query,
            str(metadata.get("name", "")),
            *[str(value) for value in metadata.get("aliases", [])],
        ])
    )
    return bool(words & TEST_ONLY_CITIES)


def load_city(
    query: str,
    slug: str,
    refresh: bool,
    bbox: tuple[float, ...] | None,
) -> tuple[list[dict], dict, Path]:
    """Reuse complete saved city files or call the existing ingest."""
    if not refresh and bbox is None:
        for folder in ("cities", "out"):
            directory = ROOT / "data" / folder / slug
            places_file = directory / "places.json"
            metadata_file = directory / "city.json"

            if places_file.is_file() and metadata_file.is_file():
                places = json.loads(
                    places_file.read_text(encoding="utf-8")
                )
                metadata = json.loads(
                    metadata_file.read_text(encoding="utf-8")
                )
                return places, metadata, directory

    result = run_city(
        query,
        cache_dir=ROOT / "data" / "cache",
        out_dir=ROOT / "data" / "out",
        contracts_dir=ROOT / "contracts",
        refresh=refresh,
        bbox=bbox,
        slug=slug,
        matrix_top=0,
    )

    directory = Path(result["out_dir"])
    metadata = json.loads(
        (directory / "city.json").read_text(encoding="utf-8")
    )
    return result["places"], metadata, directory


def build_queries(
    places: list[dict],
    currency: str,
    budgets: list[float],
    travelers: int,
    candidates: int,
    seed: int,
) -> list[dict]:
    if not isinstance(places, list) or len(places) < candidates:
        raise ValueError(
            f"At least {candidates} source places are required."
        )

    ids = [place["id"] for place in places]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate place IDs found.")

    if any(str(place_id).startswith("syn:") for place_id in ids):
        raise ValueError("Synthetic places are not allowed.")

    for place in places:
        cost = place["cost"]

        if cost["currency"] != currency:
            raise ValueError(
                f"{place['id']} uses {cost['currency']}, "
                f"but this city uses {currency}. "
                "Mixed currencies require explicit handling."
            )

        amount = float(cost["amount"])
        if not math.isfinite(amount) or amount < 0:
            raise ValueError(f"Invalid cost for {place['id']}.")

    rng = random.Random(seed)
    queries = []

    for _ in range(travelers):
        profile = _random_profile(rng)
        profile["budget"] = {
            "total": rng.choice(budgets),
            "currency": currency,
        }

        selected = rng.sample(places, candidates)
        utilities = [
            _true_utility(profile, place, rng)
            for place in selected
        ]
        grades = _graded_relevance(utilities)

        items = [
            {
                "place": place,
                "relevance": grade,
                "features": extract_features(place, profile),
            }
            for place, grade in zip(selected, grades, strict=True)
        ]

        for item in items:
            features = item["features"]
            if (
                len(features) != len(feature_names())
                or not all(math.isfinite(value) for value in features)
            ):
                raise ValueError("Invalid model features.")

        queries.append({"profile": profile, "items": items})

    return queries


def parse_bbox(value: str) -> tuple[float, ...]:
    try:
        bounds = tuple(float(part) for part in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "Use south,west,north,east."
        ) from error

    if len(bounds) != 4 or not all(map(math.isfinite, bounds)):
        raise argparse.ArgumentTypeError(
            "Provide four finite coordinates."
        )

    south, west, north, east = bounds
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise argparse.ArgumentTypeError("Invalid bounding box.")

    return bounds


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("city", help='For example "New York City, USA".')
    parser.add_argument("--slug", required=True)
    parser.add_argument(
        "--budgets",
        required=True,
        nargs="+",
        type=float,
        help="Simulated total budgets in the city's local currency.",
    )
    parser.add_argument("--travelers", type=int, default=500)
    parser.add_argument("--candidates", type=int, default=15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--bbox", type=parse_bbox)
    args = parser.parse_args()

    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", args.slug):
        parser.error("Use a lowercase city slug with no path separators.")

    if args.travelers < 2 or args.candidates < 1:
        parser.error("Use at least 2 travelers and 1 candidate.")

    if any(
        not math.isfinite(value) or value <= 0
        for value in args.budgets
    ):
        parser.error("Budgets must be finite positive numbers.")

    places, metadata, source = load_city(
        args.city, args.slug, args.refresh, args.bbox
    )

    currency = metadata.get("currency")
    if (
        not isinstance(currency, str)
        or not re.fullmatch(r"[A-Z]{3}", currency)
        or currency == "XXX"
    ):
        raise ValueError("The city has no usable currency metadata.")

    test_only = is_test_city(args.slug, args.city, metadata)
    output = ROOT / "data" / "ranking_compact" / args.slug

    if test_only and (output / "train.json").exists():
        raise ValueError(
            "A reserved test city already has a train.json in the "
            "output folder. Resolve that file before continuing."
        )

    queries = build_queries(
        places,
        currency,
        args.budgets,
        args.travelers,
        args.candidates,
        args.seed,
    )

    if test_only:
        train, test = [], queries
    else:
        train, test = split_dataset(queries, seed=args.seed)

    output.mkdir(parents=True, exist_ok=True)

    if train:
        save_dataset(output / "train.json", train)
    save_dataset(output / "test.json", test)

    summary = {
        "city": args.slug,
        "destination": metadata.get("name"),
        "source_folder": str(source),
        "source_places": len(places),
        "source_built_at": metadata.get("built_at"),
        "bbox": metadata.get("bbox"),
        "bbox_source": metadata.get("bbox_source"),
        "attribution": metadata.get("attribution"),
        "currency": currency,
        "simulated_budget_options": args.budgets,
        "seed": args.seed,
        "test_only_city": test_only,
        "train_queries": len(train),
        "test_queries": len(test),
        "candidates_per_query": args.candidates,
        "feature_names": feature_names(),
        "traveler_profiles": "Simulated.",
        "relevance_labels": "Existing synthetic utility formula.",
        "limitations": [
            "No currency conversion is performed.",
            "Budgets are supplied simulation inputs, not exchange rates.",
            "Raw-price model features are unchanged.",
            "Cross-currency model quality has not been established.",
            "Grades are not judgments from real travelers.",
            "Missing ratings and uncertain costs retain existing behavior.",
            "Only this command enforces the reserved-city policy; "
            "older datasets must not be mixed in without checking.",
        ],
    }
    save_json(output / "summary.json", summary)

    print(f"\nCity: {args.slug}")
    print(f"Currency: {currency}")
    print(f"Testing-only city: {test_only}")
    print(f"Training examples: {len(train)}")
    print(f"Testing examples: {len(test)}")
    print(f"Saved to: {output}")
    print("Model training has not been run.")


if __name__ == "__main__":
    main()