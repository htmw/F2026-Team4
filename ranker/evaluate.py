"""Measure how good the ranking is, and compare it against baselines.

Run it with:  make evaluate   (or:  uv run python -m ranker.evaluate)

The metric is NDCG@k (Normalized Discounted Cumulative Gain): a 0..1 score of how well the
model put the truly-relevant places near the top. We compare four rankers:
  - trained_model        : our LightGBM ranker
  - handcoded_dotproduct : the old scorer (interest match only)
  - popularity           : just rank by how popular a place is
  - random               : a sanity-check floor

The gap between trained_model and the baselines is the result that goes in the technical
paper — the evidence that a trained, personalized recommender actually helps.
"""

from __future__ import annotations

import lightgbm as lgb
import numpy as np

from ranker.synthetic import make_dataset
from ranker.train import DEFAULT_MODEL, train_model


def _dcg(relevances: list[float]) -> float:
    rels = np.asarray(relevances, dtype=float)
    discounts = 1.0 / np.log2(np.arange(2, len(rels) + 2))
    return float((rels * discounts).sum())


def ndcg_at_k(true_relevances: list[int], scores, k: int = 5) -> float:
    """NDCG@k for one query: rank by `scores`, reward relevant items near the top."""
    order = np.argsort(scores)[::-1][:k]
    ranked = [true_relevances[i] for i in order]
    ideal = sorted(true_relevances, reverse=True)[:k]
    ideal_dcg = _dcg(ideal)
    return _dcg(ranked) / ideal_dcg if ideal_dcg > 0 else 0.0
def precision_at_k(true_relevances: list[int], scores, k: int = 5) -> float:
    """Fraction of top-k recommendations that are relevant."""
    if k <= 0:
        return 0.0

    order = np.argsort(scores)[::-1][:k]
    relevant_count = sum(
        true_relevances[i] > 0 for i in order
    )

    return relevant_count / len(order) if len(order) else 0.0


def average_precision_at_k(true_relevances: list[int], scores, k: int = 5) -> float:
    """Average Precision@k using relevance > 0 as relevant."""
    if k <= 0:
        return 0.0

    order = np.argsort(scores)[::-1][:k]
    total_relevant = sum(r > 0 for r in true_relevances)

    if total_relevant == 0:
        return 0.0

    hits = 0
    precision_sum = 0.0

    for rank, index in enumerate(order, start=1):
        if true_relevances[index] > 0:
            hits += 1
            precision_sum += hits / rank

    return precision_sum / min(total_relevant, k)



def evaluate(
    queries: list[dict] | None = None,
    booster=None,
    k: int = 5,
) -> dict[str, float]:
    """Evaluate four ranking methods with NDCG, Precision, and MAP."""
    if queries is None:
        queries = make_dataset(seed=999)

    if booster is None:
        if not DEFAULT_MODEL.exists():
            train_model()
        booster = lgb.Booster(model_file=str(DEFAULT_MODEL))

    rng = np.random.default_rng(0)

    rankers = (
        "trained_model",
        "handcoded_dotproduct",
        "popularity",
        "random",
    )

    results = {
        f"{ranker}_{metric}@{k}": []
        for ranker in rankers
        for metric in ("ndcg", "precision", "map")
    }

    # Preserve existing NDCG result keys for older tests.
    for ranker in rankers:
        results[ranker] = []

    for q in queries:
        true = [item["relevance"] for item in q["items"]]
        feats = np.array(
            [item["features"] for item in q["items"]],
            dtype=float,
        )

        predictions = {
            "trained_model": booster.predict(feats),
            "handcoded_dotproduct": [
                item["features"][0] for item in q["items"]
            ],
            "popularity": [
                float(item["place"].get("popularity", 0.0))
                for item in q["items"]
            ],
            "random": rng.random(len(q["items"])),
        }

        for ranker, predicted_scores in predictions.items():
            ndcg = ndcg_at_k(true, predicted_scores, k)

            results[ranker].append(ndcg)
            results[f"{ranker}_ndcg@{k}"].append(ndcg)
            results[f"{ranker}_precision@{k}"].append(
                precision_at_k(true, predicted_scores, k)
            )
            results[f"{ranker}_map@{k}"].append(
                average_precision_at_k(true, predicted_scores, k)
            )

    return {
        name: float(np.mean(values)) if values else 0.0
        for name, values in results.items()
    }


def main() -> None:
    from pathlib import Path

    from ranker.dataset_io import load_dataset

    data_dir = Path("data/ranking_dataset_v3")
    test_queries = load_dataset(data_dir / "validation.json")
    print(f"Evaluating on {len(test_queries)} validation queries")

    if not DEFAULT_MODEL.exists():
        raise FileNotFoundError("Train the model before evaluating.")

    results = evaluate(queries=test_queries)

    for metric in ("ndcg@5", "precision@5", "map@5"):
        print(f"\n{metric.upper()} (higher is better):")

        matching = {
            name: value
            for name, value in results.items()
            if name.endswith(f"_{metric}")
        }

        for name, value in sorted(
            matching.items(),
            key=lambda pair: pair[1],
            reverse=True,
        ):
            ranker = name.removesuffix(f"_{metric}")
            print(f"  {ranker:22s} {value:.4f}")


if __name__ == "__main__":
    main()
