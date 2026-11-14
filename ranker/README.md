# Ranker

The ranking model scores places based on a traveler's preferences.
The optimizer uses these scores when building the itinerary.

## Train and evaluate

Run from the project root:

```bash
uv sync
uv run python -m ranker.train
uv run python -m ranker.evaluate
```

The v3 ranking dataset is stored in `data/ranking_dataset_v3/`.
It contains real OpenStreetMap places with simulated travelers and relevance grades.
Training and validation use 12 cities.
Tokyo, Bogota and Hyderabad are reserved for testing.

Training saves the model to `models/ranker.txt`.
Evaluation compares it with interest-match, popularity and random baselines
using NDCG@5, Precision@5 and MAP@5.

## Files

| File | What it does |
|---|---|
| `dataset_manifest.json` | Settings for preparing the full dataset |
| `prepare_manifest.py` | Runs dataset preparation using the settings and saved sources |
| `prepare_live.py` | Prepares examples from city data |
| `prepare_dataset.py` | Combines sources and separates training, validation and testing examples |
| `dataset_io.py` | Saves and loads compact dataset files |
| `features.py` | Calculates the numbers used by the ranking model |
| `synthetic.py` | Provides simulated traveler and relevance-label helpers |
| `train.py` | Trains the LightGBM ranking model |
| `evaluate.py` | Evaluates the model and compares it with baselines |
| `model.py` | Loads the trained model for use by the application |

See [REAL_DATA.md](REAL_DATA.md) for dataset preparation instructions.

## Application use

`model.get_scorer()` loads the trained model when it is available.
The optimizer uses it to rank candidate places alongside scheduling constraints.

If the model is missing or cannot be loaded, the optimizer uses rule-based scoring.

## Tests

```bash
uv run pytest ranker/tests -q
```
