# Model card — Wanderwise ranker

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
- **Sprint 1:** synthetic travelers and places from `ranker/synthetic.py`, with labels from
  a known hidden utility the model must recover. Lets the pipeline run with no external data.
- **Sprint 2 (current):** `data/training/dataset.json`, built by `python -m ingest.training`.
  - **Places are real:** OpenStreetMap via the live ingest (ODbL 1.0), up to 500 per city.
  - **Travelers and grades are simulated** with the formula in `ranker/synthetic.py`,
    because OpenStreetMap has no reviews or visits. Budgets are in each city's currency.
  - **Split by city:** 13 training cities (Paris, Greater London, New York, Mexico City,
    Bogotá, Kingston, Tokyo, Seoul, Bangkok, Delhi, Hyderabad, Cairo, Sydney) give 2,600
    training and 650 validation queries. 4 unseen test cities (Kyoto, Karimnagar, Nairobi,
    Columbia, US) give 1,000 test queries. Each query is one traveler ranking 15 places.

## Evaluation
- **Metric:** NDCG@5 (also Precision@k, MAP later), averaged over held-out travelers.
- **Baselines:** random, popularity-only, the hand-coded dot-product, and (later)
  an LLM-as-recommender.
- **Latest numbers (2026-11-02, `make train` then `make evaluate`):** test cities only,
  never seen in training. Early stopping picked iteration 46 (validation NDCG@5 0.773).

  | Ranker | NDCG@5 |
  |---|---:|
  | Trained model | 0.876 |
  | Hand-coded dot-product | 0.876 |
  | Popularity | 0.564 |
  | Random | 0.544 |

- **Sprint 1, for comparison (synthetic places):** trained 0.958, hand-coded 0.933,
  popularity 0.532, random 0.532.

**Reading the numbers.** On real places in cities it has never seen, the model ties the
hand-coded scorer and beats popularity and random by about 0.3. It doesn't beat the
hand-coded scorer because the grades come from a formula close to that scorer: with
simulated travelers there is nothing more to learn. The model's own importances agree:
interest match and popularity carry it, and the price and hours features are unused. To pull
ahead, it needs real preference signals: the accepted and rejected places travelers give
through `POST /trips/{id}/feedback`.

## Known limitations
- Traveler preferences and grades are simulated, so the numbers measure how well the model
  recovers the simulation, not real satisfaction.
- Price and opening-hours features get no weight yet (importance 0 to 1).
- Context features (weather, time-of-day) are stubbed, not yet used.
- Content-based only — no collaborative filtering (we have no user base by design).
