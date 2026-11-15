# Model card - Wanderwise ranker

## What it does

The model ranks candidate places based on a traveler's preferences.
The optimizer uses the ranking alongside time, budget and travel constraints
to build a day-by-day itinerary.

## Model

- Type: LightGBM LambdaRank.
- Inputs: features calculated by `ranker/features.py`.
- Output: a score for each place. Higher scores rank first.
- Training output: `models/ranker.txt`.

## Data

The v3 dataset is stored in `data/ranking_dataset_v3/`.

Places come from OpenStreetMap. Traveler profiles and relevance grades
from 0 to 4 are simulated using the existing project helpers.
Budgets use each city's local currency.

Each example contains one simulated traveler and 15 candidate places.

| Split | Examples |
|---|---:|
| Training | 4,786 |
| Validation | 1,214 |
| Testing | 1,500 |

Training and validation use separate traveler examples from 12 cities:
Paris, Lisbon, Berlin, New York, Los Angeles, Mexico City, Singapore,
Delhi, Mumbai, Cairo, Sydney and Melbourne.

Tokyo, Bogota and Hyderabad are reserved for testing.
Training and validation may share places, but identical traveler profiles
are kept separate between those two splits.

## Train and evaluate

Run from the project root:

```bash
uv sync
uv run python -m ranker.train
uv run python -m ranker.evaluate
```

## Evaluation

The following results were recorded on November 14, 2026, using the v3 dataset.
Early stopping selected iteration 37, with validation NDCG@5 of 0.7869.

Evaluation used 1,500 examples from the three reserved testing cities.
Higher values are better.

| Ranker | NDCG@5 | Precision@5 | MAP@5 |
|---|---:|---:|---:|
| Trained model | 0.8157 | 0.9393 | 0.9207 |
| Interest-match baseline | 0.8093 | 0.9392 | 0.9193 |
| Popularity | 0.6196 | 0.8324 | 0.7634 |
| Random | 0.5414 | 0.7999 | 0.7064 |

The trained model scored slightly above the interest-match baseline.
These results measure agreement with simulated relevance grades,
not real traveler satisfaction.

Earlier results used different datasets and should not be compared directly
with this run.

## Known limitations

- Traveler profiles and relevance grades are simulated.
- Some place prices and opening hours are estimated or unknown.
- Missing ratings are not replaced with real user reviews.
- Price and opening-hours features had zero split importance in this run.
- Testing uses unseen cities, but this does not guarantee every simulated
  traveler profile is unseen.
- The model uses place and traveler features, not collaborative filtering
  based on real users' behavior.

## Data source

Place data © OpenStreetMap contributors, ODbL 1.0:
https://www.openstreetmap.org/copyright
