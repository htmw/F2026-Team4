"""Serve the trained model: give the rest of the app a `score(place, profile)` function.

The API asks this module for a scorer. If a trained model file exists, it returns a
function backed by the model; if not, it returns None and the caller falls back to the
old hand-coded scorer. That fallback is what keeps the app (and CI) working before anyone
has trained a model.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ranker.features import extract_features

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "models" / "ranker.txt"


def get_scorer() -> Callable[..., float] | None:
    """Return score(place, profile, context=None) -> float, or None if no model exists."""
    if not MODEL_PATH.exists():
        return None
    try:
        import lightgbm as lgb

        booster = lgb.Booster(model_file=str(MODEL_PATH))
    except Exception:
        # If anything goes wrong loading the model, fall back rather than crash the API.
        return None

    def score(place: dict, profile: dict, context: dict | None = None) -> float:
        features = [extract_features(place, profile, context)]
        return float(booster.predict(features)[0])

    return score
