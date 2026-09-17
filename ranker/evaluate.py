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


def evaluate(queries: list[dict] | None = None, booster=None, k: int = 5) -> dict[str, float]:
    """Return the mean NDCG@k of each ranker over a set of held-out queries."""
    if queries is None:
        queries = make_dataset(seed=999)  # a different seed => unseen travelers
    if booster is None:
        if not DEFAULT_MODEL.exists():
            train_model()
        booster = lgb.Booster(model_file=str(DEFAULT_MODEL))

    rng = np.random.default_rng(0)
    scores: dict[str, list[float]] = {
        "trained_model": [],
        "handcoded_dotproduct": [],
        "popularity": [],
        "random": [],
    }
    for q in queries:
        true = [item["relevance"] for item in q["items"]]
        feats = np.array([item["features"] for item in q["items"]], dtype=float)
        model_scores = booster.predict(feats)
        dotproduct = [item["features"][0] for item in q["items"]]  # interest_match_sum
        popularity = [float(item["place"].get("popularity", 0.0)) for item in q["items"]]
        random_scores = rng.random(len(q["items"]))

        scores["trained_model"].append(ndcg_at_k(true, model_scores, k))
        scores["handcoded_dotproduct"].append(ndcg_at_k(true, dotproduct, k))
        scores["popularity"].append(ndcg_at_k(true, popularity, k))
        scores["random"].append(ndcg_at_k(true, random_scores, k))

    return {name: float(np.mean(values)) for name, values in scores.items()}


def main() -> None:
    results = evaluate()
    print("NDCG@5 over held-out travelers (higher is better):\n")
    for name, value in sorted(results.items(), key=lambda pair: pair[1], reverse=True):
        bar = "#" * int(value * 40)
        print(f"  {name:22s} {value:.3f}  {bar}")


if __name__ == "__main__":
    main()
