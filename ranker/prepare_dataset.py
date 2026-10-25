"""Prepare compact datasets from saved cities without changing the app."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

from ranker.dataset_io import save_dataset
from ranker.prepare_live import build_queries
from ranker.real_data import save_json, split_dataset

ROOT = Path(__file__).resolve().parent.parent

TRAIN_CITIES = [
    "rome",
    "amsterdam",
    "barcelona",
    "berlin",
    "bologna",
    "florence",
    "lisbon",
    "los-angeles",
    "madrid",
    "milan",
    "munich",
    "naples",
    "new-york-city",
    "paris",
    "san-francisco",
    "singapore",
    "turin",
    "venice",
    "verona",
    "vienna",
]

TEST_CITIES = ["tokyo", "bogota", "hyderabad"]


def validate_city_lists(train: list[str], test: list[str]) -> None:
    if len(train) != len(set(train)):
        raise ValueError("Duplicate training city.")

    if len(test) != len(set(test)):
        raise ValueError("Duplicate testing city.")

    overlap = set(train) & set(test)
    if overlap:
        raise ValueError(
            f"Cities appear in both sets: {sorted(overlap)}"
        )

    if not train or not test:
        raise ValueError("Training and testing cities are required.")


def find_source(root: Path, city: str) -> Path:
    """Use one saved source per city; never download anything."""
    for folder in ("cities", "out"):
        source = root / "data" / folder / city
        if (
            (source / "places.json").is_file()
            and (source / "city.json").is_file()
        ):
            return source

    raise FileNotFoundError(
        f"Complete saved data missing for {city}."
    )


def check_place_separation(
    training_ids: set[str],
    testing_ids: set[str],
) -> None:
    overlap = training_ids & testing_ids
    if overlap:
        raise ValueError(
            f"{len(overlap)} place IDs occur in both city groups. "
            f"Examples: {sorted(overlap)[:5]}"
        )


def build(
    root: Path,
    budgets: dict,
    train_cities: list[str],
    test_cities: list[str],
    travelers: int = 500,
    place_limit: int = 500,
    seed: int = 42,
) -> tuple[dict, dict]:
    """Validate sources, then generate examples with existing functions."""
    validate_city_lists(train_cities, test_cities)

    if travelers < 2 or place_limit < 15:
        raise ValueError(
            "Use at least 2 travelers and a place limit of at least 15."
        )

    sources = {}
    training_ids = set()
    testing_ids = set()

    # Check all source IDs, not just the places eventually sampled.
    for city in train_cities + test_cities:
        source = find_source(root, city)
        raw_bytes = (source / "places.json").read_bytes()
        places = json.loads(raw_bytes)
        metadata = json.loads(
            (source / "city.json").read_text(encoding="utf-8")
        )

        if not isinstance(places, list) or len(places) < 15:
            raise ValueError(f"{city}: at least 15 places required.")

        ids = [place["id"] for place in places]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{city}: duplicate place IDs.")

        currency = metadata.get("currency")
        if currency not in budgets:
            raise ValueError(
                f"{city}: no configured budgets for {currency}."
            )

        options = budgets[currency]
        if not isinstance(options, list) or not options:
            raise ValueError(
                f"{currency}: budgets must be a nonempty list."
            )

        import math

        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
            for value in options
        ):
            raise ValueError(f"{currency}: invalid budget values.")

        for place in places:
            if place["cost"]["currency"] != currency:
                raise ValueError(
                    f"{city}: mixed or mismatched currencies."
                )

        target = (
            training_ids if city in train_cities else testing_ids
        )
        target.update(ids)

        sources[city] = {
            "places": places,
            "metadata": metadata,
            "path": source,
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        }

    check_place_separation(training_ids, testing_ids)

    datasets = {"train": [], "validation": [], "test": []}
    provenance = []

    for city in train_cities + test_cities:
        entry = sources[city]
        places = sorted(entry["places"], key=lambda p: p["id"])
        city_seed = int.from_bytes(
            hashlib.sha256(
                f"{seed}:{city}".encode()
            ).digest()[:8],
            "big",
        )

        if len(places) > place_limit:
            places = random.Random(city_seed).sample(
                places, place_limit
            )
            places.sort(key=lambda p: p["id"])

        currency = entry["metadata"]["currency"]
        queries = build_queries(
            places,
            currency,
            budgets[currency],
            travelers,
            15,
            city_seed,
        )

        if city in test_cities:
            datasets["test"].extend(queries)
            role = "test-only"
        else:
            train, validation = split_dataset(queries, seed=seed)
            datasets["train"].extend(train)
            datasets["validation"].extend(validation)
            role = "training-development"

        provenance.append({
            "city": city,
            "role": role,
            "currency": currency,
            "source_folder": str(entry["path"].relative_to(root)),
            "source_sha256": entry["sha256"],
            "source_places": len(entry["places"]),
            "sampled_places": len(places),
            "bbox": entry["metadata"].get("bbox"),
            "attribution": entry["metadata"].get("attribution"),
        })
        print(f"{city}: prepared ({role})", flush=True)

    # Check traveler separation across the combined development data.
    def profile_keys(queries):
        return {
            json.dumps(q["profile"], sort_keys=True)
            for q in queries
        }

    if (
        profile_keys(datasets["train"])
        & profile_keys(datasets["validation"])
    ):
        raise ValueError("Training/validation profiles overlap.")

    summary = {
        "train_cities": train_cities,
        "test_only_cities": test_cities,
        "travelers_per_city": travelers,
        "maximum_places_per_city": place_limit,
        "candidates_per_traveler": 15,
        "seed": seed,
        "simulated_budget_options": budgets,
        "counts": {
            split: len(queries)
            for split, queries in datasets.items()
        },
        "source_place_overlap_between_city_groups": 0,
        "sources": provenance,
        "limitations": [
            "Travelers and relevance grades are simulated.",
            "Budgets are explicit simulation inputs, not exchange rates.",
            "Existing model features and label formula are unchanged.",
            "Validation uses travelers from training cities.",
            "Final testing uses reserved cities only.",
            "City-held-out testing does not guarantee unseen travelers.",
            "Unknown prices and missing ratings retain existing behavior.",
            "Cross-currency model performance has not been evaluated.",
        ],
    }
    return datasets, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budgets-file", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "ranking_dataset_v2",
    )
    parser.add_argument("--travelers", type=int, default=500)
    parser.add_argument("--place-limit", type=int, default=500)
    args = parser.parse_args()

    if args.output.exists():
        parser.error(
            "Output folder already exists. Choose a new --output "
            "to preserve the previous dataset."
        )

    budgets = json.loads(
        args.budgets_file.read_text(encoding="utf-8")
    )
    if not isinstance(budgets, dict):
        parser.error("Budget configuration must be a JSON object.")

    datasets, summary = build(
        ROOT,
        budgets,
        TRAIN_CITIES,
        TEST_CITIES,
        travelers=args.travelers,
        place_limit=args.place_limit,
    )

    for split, queries in datasets.items():
        save_dataset(args.output / f"{split}.json", queries)

    save_json(args.output / "summary.json", summary)

    print("\nPreparation finished.")
    for split, queries in datasets.items():
        print(f"{split}: {len(queries)} examples")
    print(f"Saved to: {args.output}")
    print("No downloads, app changes or model training ran.")


if __name__ == "__main__":
    main()