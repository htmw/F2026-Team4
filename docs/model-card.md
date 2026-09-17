# Model card — travel-recommender ranker

A short, honest description of the trained model. Update it as the model changes.

## What it does
Given a traveler and a set of candidate places, predict a score per place so the app can
**rank** them by fit. It replaces a hand-coded scorer; a deterministic optimizer then
schedules the top-ranked places into a day-by-day itinerary.

## Model
- **Type:** LightGBM, `objective="lambdarank"` (learning-to-rank, gradient-boosted trees).
- **Inputs:** the content-based feature vector defined in `ranker/features.py`.
- **Output:** a real-valued score; higher = better fit. Only the *order* matters.
- **Training:** CPU, minutes, `make train`.

## Data
- **Sprint 1:** synthetic travelers + labels from `ranker/synthetic.py` (a known hidden
  utility the model must recover). Lets the pipeline run with no external data.
- **Sprint 2+:** a real public dataset (candidate: Yelp Open Dataset) mapped onto the same
  feature schema. _Record the exact source, size, and split here when adopted._

## Evaluation
- **Metric:** NDCG@5 (also Precision@k, MAP later), averaged over held-out travelers.
- **Baselines:** random, popularity-only, the hand-coded dot-product, and (Sprint 2)
  an LLM-as-recommender.
- **Latest numbers:** _paste `make evaluate` output here each sprint._

## Known limitations
- Synthetic data is a simplification of real preferences (Sprint 1 only).
- Context features (weather, time-of-day) are stubbed, not yet used.
- Content-based only — no collaborative filtering (we have no user base by design).
