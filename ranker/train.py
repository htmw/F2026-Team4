"""Train and validate the WanderWise LightGBM ranking model."""

from __future__ import annotations

from pathlib import Path

import lightgbm as lgb
import numpy as np

from ranker.features import feature_names
from ranker.synthetic import make_dataset, to_matrix

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = ROOT / "models" / "ranker.txt"


def train_model(
    queries: list[dict] | None = None,
    out_path: Path = DEFAULT_MODEL,
    seed: int = 0,
    validation_queries: list[dict] | None = None,
) -> lgb.Booster:
    """Train LambdaRank with a separate validation set."""

    if queries is None:
        queries = make_dataset(seed=seed)

    if validation_queries is not None:
        train_queries = queries
        val_queries = validation_queries

        if not train_queries or not val_queries:
            raise ValueError("Training and validation queries must not be empty.")
    else:
        if len(queries) < 2:
            raise ValueError("At least two traveler queries are required.")

        # Preserve the original Sprint 1 behavior.
        rng = np.random.default_rng(seed)
        indices = rng.permutation(len(queries))
        split = max(1, min(len(indices) - 1, int(len(indices) * 0.8)))

        train_queries = [queries[i] for i in indices[:split]]
        val_queries = [queries[i] for i in indices[split:]]

    x_train, y_train, group_train = to_matrix(train_queries)
    x_val, y_val, group_val = to_matrix(val_queries)

    # Training dataset
    train_data = lgb.Dataset(
        x_train,
        label=y_train,
        group=group_train,
        feature_name=feature_names(),
    )

    # Validation dataset
    validation_data = lgb.Dataset(
        x_val,
        label=y_val,
        group=group_val,
        reference=train_data,
    )

    params = {
        "objective": "lambdarank",
        "metric": "ndcg",
        "ndcg_eval_at": [5],
        "learning_rate": 0.05,
        "num_leaves": 11,
        "min_data_in_leaf": 10,
        "num_threads": 1,
        "seed": seed,
        "verbosity": -1,
    }

    # Train using early stopping
    booster = lgb.train(
        params,
        train_data,
        num_boost_round=300,
        valid_sets=[validation_data],
        valid_names=["validation"],
        callbacks=[
            lgb.early_stopping(20),
            lgb.log_evaluation(25),
        ],
    )

    # Save trained model
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(out_path))

    return booster


def main() -> None:
    from ingest.training import load_queries
    from ranker.dataset_io import load_dataset

    data_dir = ROOT / "data" / "ranking_dataset_v3"

    if all((data_dir / f"{split}.json").is_file() for split in ("train", "validation", "test")):
        train_queries = load_dataset(data_dir / "train.json")
        validation_queries = load_dataset(data_dir / "validation.json")
        print("Using v3 dataset.")
    else:
        print("v3 dataset not found. Using committed training dataset.")
        train_queries = load_queries("train")
        validation_queries = load_queries("validation")

    print(f"Training queries: {len(train_queries)}")
    print(f"Validation queries: {len(validation_queries)}")

    booster = train_model(
        queries=train_queries,
        validation_queries=validation_queries,
    )

    source = (
        "v3"
        if all((data_dir / f"{split}.json").is_file() for split in ("train", "validation", "test"))
        else "committed"
    )

    (ROOT / "models" / "ranker.dataset_source").write_text(source, encoding="utf-8")

    print(f"Trained LightGBM ranker -> {DEFAULT_MODEL}")
    print(f"Best iteration: {booster.best_iteration}")

    print("\nFeature importances:")
    for name, importance in sorted(
        zip(feature_names(), booster.feature_importance(), strict=True),
        key=lambda item: item[1],
        reverse=True,
    ):
        print(f"  {name:20s} {importance}")


if __name__ == "__main__":
    main()
