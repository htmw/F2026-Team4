"""Exercise the standalone preparation sample against current project code."""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

from ranker.dataset_io import load_dataset, save_dataset
from ranker.evaluate import evaluate
from ranker.features import extract_features, feature_names
from ranker.prepare_dataset import build
from ranker.train import train_model

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "ranker" / "examples"


def sample_queries():
    manifest = json.loads((EXAMPLES / "manifest.json").read_text(encoding="utf-8"))
    return build(
        EXAMPLES / "snapshots",
        manifest["budgets"],
        [c["key"] for c in manifest["cities"] if c["role"] == "train"],
        [c["key"] for c in manifest["cities"] if c["role"] == "test"],
        travelers=manifest["travelers_per_city"],
        place_limit=manifest["maximum_places_per_city"],
        seed=manifest["seed"],
    )[0]


def test_sample_cli_rebuilds_identical_files_offline(tmp_path):
    outputs = [tmp_path / "first", tmp_path / "second"]
    for output in outputs:
        result = subprocess.run(
            [
                sys.executable, "-m", "ranker.prepare_manifest",
                "--manifest", str(EXAMPLES / "manifest.json"),
                "--snapshots", str(EXAMPLES / "snapshots"),
                "--offline", "--output", str(output),
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONHASHSEED": "0", "WANDERWISE_LIVE_INGEST": "0"},
            capture_output=True,
            text=True,
            check=True,
        )
        assert "No app files changed. No model training ran." in result.stdout

    expected = {"manifest.json", "summary.json", "train.json", "validation.json", "test.json"}
    assert {p.name for p in outputs[0].iterdir()} == expected
    for name in expected:
        assert (outputs[0] / name).read_bytes() == (outputs[1] / name).read_bytes()


def test_compact_sample_uses_current_features_and_preserves_cost_confidence(tmp_path):
    for split, queries in sample_queries().items():
        path = tmp_path / f"{split}.json"
        save_dataset(path, queries)
        restored = load_dataset(path)
        for before, after in zip(queries, restored, strict=True):
            for original, item in zip(before["items"], after["items"], strict=True):
                assert item["place"]["cost"] == original["place"]["cost"]
                assert item["features"] == extract_features(item["place"], after["profile"])
                index = feature_names().index("price_ratio")
                assert item["features"][index] == (
                    item["place"]["cost"]["amount"] / after["profile"]["budget"]["total"]
                )


def test_loaded_sample_is_accepted_by_model_functions(tmp_path):
    loaded = {}
    for split, queries in sample_queries().items():
        path = tmp_path / f"{split}.json"
        save_dataset(path, queries)
        loaded[split] = load_dataset(path)
    booster = train_model(
        queries=loaded["train"],
        validation_queries=loaded["validation"],
        out_path=tmp_path / "model.txt",
    )
    results = evaluate(queries=loaded["test"], booster=booster)
    assert results
    assert all(math.isfinite(value) and 0 <= value <= 1 for value in results.values())
