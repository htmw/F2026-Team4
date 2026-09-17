# /ranker — the trained recommender (Model & Ranking team, 2 people)

**You own the ML core:** a model we *train* to rank places for a traveler.

## Run it
```bash
make train       # trains a LightGBM ranker on synthetic data -> models/ranker.txt
make evaluate    # prints NDCG@5 for the model vs baselines
```

## The pieces
| File | What it does |
|------|--------------|
| [`features.py`](features.py) | turns a `(place, traveler)` pair into a fixed list of numbers the model learns from |
| [`synthetic.py`](synthetic.py) | invents travelers + labels so the whole loop runs with zero downloads (Sprint 1) |
| [`train.py`](train.py) | trains the LightGBM LambdaRank model, saves `models/ranker.txt` |
| [`evaluate.py`](evaluate.py) | scores the model vs popularity / hand-coded / random (NDCG@k) |
| [`model.py`](model.py) | serves it: hands the API a `score(place, profile)` function |

## The contract boundary
- **In:** a `TravelerProfile` + `Place[]` (the shapes in [`/contracts`](../contracts)).
- **Out:** a number per place. `model.get_scorer()` returns a drop-in for the hand-coded
  `score()` in [`api/scheduler_stub.py`](../api/scheduler_stub.py) — when a trained model
  exists, the API uses it automatically; otherwise it falls back to the stub.

## The roadmap
- **Sprint 1:** synthetic data → first trained model end-to-end → NDCG beats popularity.
- **Sprint 2:** swap synthetic for a real public dataset (e.g. Yelp), add real features,
  add the LLM-as-recommender baseline. Write the comparison table → the technical paper.
- **Sprint 3:** tune; optional neural two-tower model as a second experiment; ablations.

Every change ships with the number it moved (NDCG@k) in [`/docs`](../docs).