
import json
from pathlib import Path

from api.contracts import load_places
from ranker.model import get_scorer

ROOT = Path(__file__).resolve().parents[2]


def load_profile():
    with open(ROOT / "fixtures" / "sample.profile.json", encoding="utf-8") as f:
        return json.load(f)


def rank_places(profile, scorer):
    places = load_places("lisbon")
    return sorted(places, key=lambda place: scorer(place, profile), reverse=True)


def test_model_loads():
    scorer = get_scorer()
    assert scorer is not None, "Train the model before running this test"


def test_model_scores_places():
    scorer = get_scorer()
    assert scorer is not None, "Train the model before running this test"

    profile = load_profile()
    places = load_places("lisbon")

    assert len(places) > 0

    for place in places:
        score = scorer(place, profile)
        assert isinstance(score, float)


def test_history_and_food_have_different_rankings():
    scorer = get_scorer()
    assert scorer is not None, "Train the model before running this test"

    base = load_profile()

    history_profile = json.loads(json.dumps(base))
    food_profile = json.loads(json.dumps(base))

    history_profile["interests"] = {
        interest: (1.0 if interest == "history" else 0.0)
        for interest in base["interests"]
    }
    food_profile["interests"] = {
        interest: (1.0 if interest == "food" else 0.0)
        for interest in base["interests"]
    }

    history_top_5 = [
        place["id"] for place in rank_places(history_profile, scorer)[:5]
    ]
    food_top_5 = [
        place["id"] for place in rank_places(food_profile, scorer)[:5]
    ]

    assert history_top_5 != food_top_5
