# Training data for the ranker

Owner: Data team. Built by [`ingest/training.py`](../ingest/training.py).

## Why a frozen file

The app fetches cities live. Training cannot: two models are only comparable when they are
trained and tested on the same data. So the training data is a fixed file,
`data/training/dataset.json`, built once from cities the live ingest already saved in
`data/live/`. Building it never calls OpenStreetMap.

```bash
uv run python -m ingest.training
```

## What is in it

| Part | Source |
|------|--------|
| Places | Real OpenStreetMap records from the live ingest, up to 500 per city, sampled with a fixed seed so sights and cafes both stay in |
| Travelers | Simulated, 120 per city (`ranker.synthetic`) |
| Grades 0..4 | Simulated with the ranker's own synthetic formula. OSM has no reviews, so these are not real travelers' judgments |

**Train cities (13):** Paris, London, New York, Mexico City, Bogotá, Kingston, Tokyo, Seoul,
Bangkok, Delhi, Hyderabad, Cairo, Sydney.

**Test cities (4), never trained on:** Kyoto, Karimnagar, Nairobi, Columbia. They differ in
size and region, so the test asks whether the model works in a city it has not seen, which is
what the content-based features in `ranker/features.py` are meant to allow.

Each place is stored once and travelers refer to places by id, so the file stays a few MB.
`load_queries("train")` and `load_queries("test")` rebuild the shape
`ranker.synthetic.make_dataset()` returns, so `ranker/train.py` and `ranker/evaluate.py` take
it without changes.

## Limits

- Grades are simulated. Real labels need a public review dataset such as Yelp, which only
  covers some North American cities.
- Real OSM places carry no `rating`, so the `rating_norm` feature is always 0 here.
- Places come from 5 km around each city centre, as the live ingest fetches them.
