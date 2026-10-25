"""Freeze live-fetched cities into one small training file for the ranker.

Training has to use the same data on every run, otherwise two models cannot be compared.
The app keeps fetching live; this only reads what earlier live fetches saved in data/live/
and never goes to OpenStreetMap itself.

    uv run python -m ingest.training        # writes data/training/dataset.json

Places are real (OSM). Travelers and their grades are simulated with the ranker's own
synthetic formula, because OSM has no reviews; their budgets are in the city's currency.
Test cities are never used for training, so the test asks whether the model works in a
city it has not seen.

Each place is stored once and travelers refer to places by id, which keeps the file a few
MB. load_queries() rebuilds the shape ranker.synthetic.make_dataset() returns, so
ranker/train.py and ranker/evaluate.py take it unchanged.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from ranker.features import extract_features
from ranker.synthetic import _graded_relevance, _random_profile, _true_utility

from .cache import write_json

ROOT = Path(__file__).resolve().parent.parent
LIVE_DIR = ROOT / "data" / "live"
OUT = ROOT / "data" / "training" / "dataset.json"

TRAIN_CITIES = [
    "paris-fr",
    "greater-london-gb",
    "new-york-us",
    "mexico-city-mx",
    "bogota-co",
    "kingston-jm",
    "tokyo-jp",
    "seoul-kr",
    "bangkok-th",
    "delhi-in",
    "hyderabad-in",
    "cairo-eg",
    "sydney-au",
]
# Unseen cities of different sizes and regions: is the model any good somewhere new?
TEST_CITIES = ["kyoto-jp", "karimnagar-in", "nairobi-ke", "columbia-us"]

PER_CITY = 500  # places kept per city
TRAVELERS = 120  # simulated travelers per city
CANDIDATES = 15  # places each traveler ranks
SEED = 0  # same input, same file

# Travelers get budgets in the city's own money, so price_fits_budget compares like with
# like (a 1,000 yen ticket against a 30,000 yen budget, not against 300). The EUR options
# are ranker.synthetic's; each currency's factor is a rough October 2026 rate, used only to
# set simulation budgets, never to convert a price.
EUR_BUDGETS = [300, 600, 1200, 2000]
BUDGET_FACTOR = {
    "EUR": 1,
    "GBP": 0.85,
    "USD": 1.1,
    "AUD": 1.65,
    "MXN": 20,
    "COP": 4500,
    "JMD": 170,
    "JPY": 165,
    "KRW": 1500,
    "THB": 38,
    "INR": 92,
    "EGP": 53,
    "KES": 140,
}


def local_budgets(currency: str) -> list[float]:
    if currency not in BUDGET_FACTOR:
        raise ValueError(f"No budget factor for {currency}. Add it to BUDGET_FACTOR.")
    return [round(b * BUDGET_FACTOR[currency], 2) for b in EUR_BUDGETS]


def compact(place: dict) -> dict:
    """Only what ranker/features.py and the popularity baseline read."""
    return {
        "id": place["id"],
        "name": place["name"],
        "categories": place["categories"],
        "typical_duration_minutes": place["typical_duration_minutes"],
        "cost": place["cost"],
        "hours": {"confidence": place["hours"]["confidence"]},
        "popularity": place.get("popularity", 0.0),
    }


def sample_places(places: list[dict], per_city: int, rng: random.Random) -> list[dict]:
    """A random but repeatable sample, so sights and cafes both stay in."""
    places = sorted(places, key=lambda p: p["id"])
    if len(places) > per_city:
        places = sorted(rng.sample(places, per_city), key=lambda p: p["id"])
    return [compact(p) for p in places]


def make_queries(city: str, places: list[dict], travelers: int, rng: random.Random) -> list:
    currency = places[0]["cost"]["currency"]
    budgets = local_budgets(currency)
    queries = []
    for _ in range(travelers):
        profile = _random_profile(rng)
        profile["budget"] = {"total": rng.choice(budgets), "currency": currency}
        candidates = rng.sample(places, min(CANDIDATES, len(places)))
        grades = _graded_relevance([_true_utility(profile, p, rng) for p in candidates])
        items = [
            {"place_id": p["id"], "relevance": g}
            for p, g in zip(candidates, grades, strict=True)
        ]
        queries.append({"city": city, "profile": profile, "items": items})
    return queries


def build(
    live_dir: Path,
    train: list[str],
    test: list[str],
    per_city: int = PER_CITY,
    travelers: int = TRAVELERS,
) -> dict:
    missing = [c for c in train + test if not (live_dir / c / "places.json").exists()]
    if missing:
        raise FileNotFoundError(
            f"Not fetched yet: {', '.join(missing)}. Plan a trip to each once in the app."
        )
    rng = random.Random(SEED)
    cities, queries = {}, {"train": [], "test": []}
    for split, keys in (("train", train), ("test", test)):
        for key in keys:
            raw = json.loads((live_dir / key / "places.json").read_text(encoding="utf-8"))
            cities[key] = sample_places(raw, per_city, rng)
            queries[split] += make_queries(key, cities[key], travelers, rng)
    return {
        "source": "Places: OpenStreetMap via the live ingest (ODbL 1.0). "
        "Travelers and grades: simulated with ranker.synthetic.",
        "train_cities": train,
        "test_cities": test,
        "cities": cities,
        **queries,
    }


def load_queries(split: str, path: Path = OUT) -> list[dict]:
    """The train or test queries, in the shape ranker.synthetic.make_dataset() returns."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    places = {p["id"]: p for city in data["cities"].values() for p in city}
    out = []
    for q in data[split]:
        items = []
        for item in q["items"]:
            place = places[item["place_id"]]
            features = extract_features(place, q["profile"])
            items.append({"place": place, "relevance": item["relevance"], "features": features})
        out.append({"profile": q["profile"], "items": items})
    return out


def main() -> int:
    try:
        data = build(LIVE_DIR, TRAIN_CITIES, TEST_CITIES)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_json(OUT, data)
    print(f"train: {len(data['train'])} travelers from {len(data['train_cities'])} cities")
    print(f"test:  {len(data['test'])} travelers from {len(data['test_cities'])} unseen cities")
    print(f"-> {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
