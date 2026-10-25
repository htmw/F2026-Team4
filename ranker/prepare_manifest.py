"""Prepare a manifest-selected dataset using saved source snapshots.

The existing live catalog is called only when a snapshot is missing.
No application files are modified. Model training is separate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path

from ranker.dataset_io import compact_place, save_dataset
from ranker.prepare_dataset import (
    build,
    check_place_separation,
    validate_city_lists,
)
from ranker.real_data import save_json

ROOT = Path(__file__).resolve().parent.parent


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_hash(value) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_manifest(manifest: dict) -> None:
    if manifest.get("version") != 1:
        raise ValueError("Unsupported manifest version.")

    cities = manifest.get("cities")
    if not isinstance(cities, list) or not cities:
        raise ValueError("Manifest needs a nonempty city list.")

    keys = []
    for city in cities:
        key = city["key"]

        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", key):
            raise ValueError(f"Invalid city key: {key}")

        if city["role"] not in {"train", "test"}:
            raise ValueError(f"Invalid role for {key}.")

        if not isinstance(city.get("query"), str) or not city["query"].strip():
            raise ValueError(f"Missing city query for {key}.")

        if city["currency"] not in manifest["budgets"]:
            raise ValueError(f"No budget configuration for {key}.")

        keys.append(key)

    if len(keys) != len(set(keys)):
        raise ValueError("Manifest city keys must be unique.")

    train = [c["key"] for c in cities if c["role"] == "train"]
    test = [c["key"] for c in cities if c["role"] == "test"]
    validate_city_lists(train, test)

    if manifest["candidates_per_traveler"] != 15:
        raise ValueError("Current builder requires 15 candidates.")

    if manifest["maximum_places_per_city"] < 15:
        raise ValueError("Keep at least 15 places per city.")

    if manifest["travelers_per_city"] < 2:
        raise ValueError("Use at least two travelers per city.")

    import math

    for currency, options in manifest["budgets"].items():
        if not isinstance(options, list) or not options:
            raise ValueError(f"Missing budget options for {currency}.")

        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
            for value in options
        ):
            raise ValueError(f"Invalid budget options for {currency}.")


def verify_snapshot(
    folder: Path,
    spec: dict,
    settings: dict,
) -> dict:
    lock = json.loads(
        (folder / "snapshot.json").read_text(encoding="utf-8")
    )

    if lock["city_spec"] != spec or lock["sampling"] != settings:
        raise ValueError(
            f"{spec['key']}: snapshot configuration differs. "
            "Choose a new snapshots folder."
        )

    for filename, expected in lock["files"].items():
        if file_hash(folder / filename) != expected:
            raise ValueError(
                f"{spec['key']}: snapshot checksum failed for {filename}."
            )

    return lock


def ensure_snapshot(
    snapshots: Path,
    spec: dict,
    place_limit: int,
    seed: int,
    offline: bool,
) -> dict:
    key = spec["key"]
    folder = snapshots / "data" / "out" / key
    settings = {
        "maximum_places": place_limit,
        "seed": seed,
    }

    if folder.exists():
        return verify_snapshot(folder, spec, settings)

    if offline:
        raise FileNotFoundError(f"No saved snapshot for {key}.")

    # Use the existing implementation, without modifying it.
    from ingest.catalog import fetch_live

    source = fetch_live(spec["query"])
    places_file = source / "places.json"
    metadata_file = source / "city.json"

    raw_bytes = places_file.read_bytes()
    places = json.loads(raw_bytes)
    metadata = json.loads(
        metadata_file.read_text(encoding="utf-8")
    )

    if metadata.get("country", "").upper() != spec["country"].upper():
        raise ValueError(f"{key}: fetched country does not match manifest.")

    if metadata.get("currency") != spec["currency"]:
        raise ValueError(f"{key}: fetched currency does not match manifest.")

    if not isinstance(places, list) or len(places) < 15:
        raise ValueError(f"{key}: at least 15 source places required.")

    ids = [place["id"] for place in places]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{key}: duplicate source place IDs.")

    for place in places:
        if place["cost"]["currency"] != spec["currency"]:
            raise ValueError(f"{key}: mixed source currencies.")

    ordered = sorted(places, key=lambda place: place["id"])
    city_seed = int.from_bytes(
        hashlib.sha256(
            f"{seed}:{key}".encode("utf-8")
        ).digest()[:8],
        "big",
    )

    if len(ordered) > place_limit:
        ordered = random.Random(city_seed).sample(
            ordered, place_limit
        )
        ordered.sort(key=lambda place: place["id"])

    # These snapshots are ranking inputs, not full app Place records.
    selected = [compact_place(place) for place in ordered]

    temporary = folder.with_name(folder.name + ".pending")
    if temporary.exists():
        raise ValueError(
            f"An unfinished snapshot exists: {temporary}. "
            "Inspect it before retrying."
        )

    temporary.mkdir(parents=True)
    save_json(temporary / "places.json", selected)
    save_json(temporary / "city.json", metadata)

    # Keep all source IDs so separation is checked before sampling.
    save_json(temporary / "source_ids.json", sorted(ids))

    filenames = ["places.json", "city.json", "source_ids.json"]
    lock = {
        "city_spec": spec,
        "sampling": settings,
        "resolved_name": metadata.get("name"),
        "resolved_source_key": source.name,
        "source_built_at": metadata.get("built_at"),
        "source_places": len(places),
        "selected_places": len(selected),
        "original_places_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "bbox": metadata.get("bbox"),
        "attribution": metadata.get("attribution"),
        "files": {
            name: file_hash(temporary / name)
            for name in filenames
        },
    }
    save_json(temporary / "snapshot.json", lock)
    temporary.rename(folder)
    return lock


def check_source_ids(snapshots: Path, cities: list[dict]) -> None:
    training = set()
    testing = set()

    for spec in cities:
        path = (
            snapshots / "data" / "out"
            / spec["key"] / "source_ids.json"
        )
        ids = json.loads(path.read_text(encoding="utf-8"))
        target = training if spec["role"] == "train" else testing
        target.update(ids)

    check_place_separation(training, testing)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "ranker" / "dataset_manifest.json",
    )
    parser.add_argument(
        "--snapshots",
        type=Path,
        default=ROOT / "data" / "ranking_sources_v3",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "ranking_dataset_v3",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Require saved snapshots; do not contact OSM.",
    )
    args = parser.parse_args()

    # Stabilize set iteration used by existing feature/label helpers.
    if os.environ.get("PYTHONHASHSEED") != "0":
        environment = dict(os.environ)
        environment["PYTHONHASHSEED"] = "0"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ranker.prepare_manifest",
                *sys.argv[1:],
            ],
            env=environment,
            check=False,
        )
        raise SystemExit(result.returncode)

    if os.environ.get("WANDERWISE_RANKING_BUDGETS"):
        parser.error(
            "Remove the old app-hook environment setting first. "
            "This command uses manifest budgets only."
        )

    if args.output.exists():
        parser.error("Output exists. Choose a new --output folder.")

    manifest = json.loads(
        args.manifest.read_text(encoding="utf-8")
    )
    validate_manifest(manifest)

    train = [
        city["key"]
        for city in manifest["cities"]
        if city["role"] == "train"
    ]
    test = [
        city["key"]
        for city in manifest["cities"]
        if city["role"] == "test"
    ]

    snapshot_locks = []
    for spec in manifest["cities"]:
        print(f"\nChecking source: {spec['key']}", flush=True)
        lock = ensure_snapshot(
            args.snapshots,
            spec,
            manifest["maximum_places_per_city"],
            manifest["seed"],
            args.offline,
        )
        snapshot_locks.append(lock)

    check_source_ids(args.snapshots, manifest["cities"])

    datasets, summary = build(
        args.snapshots,
        manifest["budgets"],
        train,
        test,
        travelers=manifest["travelers_per_city"],
        place_limit=manifest["maximum_places_per_city"],
        seed=manifest["seed"],
    )

    summary["manifest_sha256"] = object_hash(manifest)
    summary["snapshot_provenance"] = snapshot_locks
    summary["python_hash_seed"] = 0
    summary["full_source_place_id_overlap"] = 0
    summary["rebuild_note"] = (
        "Exact comparison requires these snapshots, manifest, matching "
        "code and dependencies. Fresh OSM fetches may produce different data."
    )
    summary["code_sha256"] = {
        name: file_hash(ROOT / "ranker" / name)
        for name in (
            "prepare_manifest.py",
            "prepare_dataset.py",
            "prepare_live.py",
            "dataset_io.py",
            "real_data.py",
            "features.py",
            "synthetic.py",
        )
    }

    # Publish to the requested output only after all files are written.
    temporary = args.output.with_name(args.output.name + ".pending")
    if temporary.exists():
        parser.error(
            f"Unfinished output exists: {temporary}. Inspect it first."
        )

    temporary.mkdir(parents=True)
    for split, queries in datasets.items():
        save_dataset(temporary / f"{split}.json", queries)

    save_json(temporary / "summary.json", summary)
    save_json(temporary / "manifest.json", manifest)
    temporary.rename(args.output)

    print("\nPreparation complete.")
    print(f"Training/development cities: {len(train)}")
    print(f"Testing-only cities: {len(test)}")
    for split, queries in datasets.items():
        print(f"{split}: {len(queries)} examples")
    print(f"Dataset: {args.output}")
    print(f"Rebuild snapshots: {args.snapshots}")
    print("No app files changed. No model training ran.")


if __name__ == "__main__":
    main()