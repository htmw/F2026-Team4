"""Train the learning-to-rank model and save it to models/ranker.txt.

Run it with:  make train   (or:  uv run python -m ranker.train)

This is deliberately small and CPU-only. The Model team's job is to grow it: better
features, real data, hyper-parameter tuning, the evaluation in evaluate.py.
"""

from __future__ import annotations

from pathlib import Path

import lightgbm as lgb

from ranker.features import feature_names
from ranker.synthetic import make_dataset, to_matrix

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = ROOT / "models" / "ranker.txt"


def train_model(
    queries: list[dict] | None = None,
    out_path: Path = DEFAULT_MODEL,
    seed: int = 0,
) -> lgb.Booster:
    """Train a LightGBM LambdaRank model and save it. Returns the fitted booster."""
    if queries is None:
        queries = make_dataset(seed=seed)
    x, y, group = to_matrix(queries)

    dataset = lgb.Dataset(x, label=y, group=group, feature_name=feature_names())
    params = {
        "objective": "lambdarank",   # the standard learning-to-rank objective
        "metric": "ndcg",
        "ndcg_eval_at": [5],
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_data_in_leaf": 10,
        "num_threads": 1,            # single-threaded => reproducible
        "seed": seed,
        "verbosity": -1,
    }
    booster = lgb.train(params, dataset, num_boost_round=200)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(out_path))
    return booster


def main() -> None:
    booster = train_model()
    print(f"Trained LightGBM ranker -> {DEFAULT_MODEL.relative_to(ROOT)}")
    print("\nFeature importances (what the model leaned on most):")
    ranked = sorted(
        zip(feature_names(), booster.feature_importance(), strict=True),
        key=lambda pair: pair[1],
        reverse=True,
    )
    for name, importance in ranked:
        print(f"  {name:20s} {int(importance)}")


if __name__ == "__main__":
    main()
