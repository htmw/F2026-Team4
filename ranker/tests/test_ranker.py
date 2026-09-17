"""Tests for the ranking model pipeline.

These guard the ML core: features stay aligned, and a trained model must beat the naive
baselines on held-out data (otherwise training is pointless).
"""

from __future__ import annotations

from ranker.evaluate import evaluate, ndcg_at_k
from ranker.features import extract_features, feature_names
from ranker.synthetic import make_dataset
from ranker.train import train_model


def test_feature_vector_matches_feature_names():
    query = make_dataset(n_travelers=1, k=5, seed=1)[0]
    features = extract_features(query["items"][0]["place"], query["profile"])
    assert len(features) == len(feature_names())


def test_ndcg_is_perfect_when_scores_match_relevance():
    true = [0, 1, 2, 3, 4]
    assert ndcg_at_k(true, scores=true, k=5) == 1.0


def test_trained_model_beats_baselines(tmp_path):
    train_queries = make_dataset(n_travelers=100, seed=1)
    booster = train_model(train_queries, out_path=tmp_path / "ranker.txt", seed=1)

    test_queries = make_dataset(n_travelers=50, seed=2)
    results = evaluate(test_queries, booster=booster)

    # The whole point: a trained, personalized ranker should beat popularity and random.
    assert results["trained_model"] >= results["popularity"]
    assert results["trained_model"] >= results["random"]
