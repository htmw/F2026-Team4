# Design & Architecture

Read this before working in the repo. It is the source of truth for how the system fits
together and the data shapes every part speaks.

---

## What this project is

A personalized travel itinerary planner. The user says where they're going, how long they
have, and what they care about. The system produces a day-by-day schedule that is **actually
executable**: real opening hours, real travel times between stops, real costs, and lets the
user modify it in natural language.

**A trained model ranks the places. A deterministic optimizer schedules them. The LLM only
handles language.** Three separate jobs, and we never let one do another's work:

- **Trained recommender (our ML model):** a learning-to-rank model we train predicts how well
  each place fits a given traveler and context. This is the heart of the project.
- **Deterministic optimizer:** takes the ranked places and packs them into a day-by-day
  schedule that respects opening hours, travel time, budget, and pace. Plain, testable code.
- **LLM:** turns free text into a `TravelerProfile`, turns edit
  requests into structured changes, and writes explanations. It is **never** the source of
  truth for opening hours, travel times, distances, prices, availability, scores, or which
  places end up in the itinerary.

If you ever find yourself about to ask a generative model to "generate an itinerary," stop,
that is the failure mode this project exists to avoid.

---

## Architecture

```
  Preference form  ──┐
                     ├──►  TravelerProfile  ──┐
  Free text  ──► LLM ┘        (structured)    │
                                              ▼
  Destination name ──► Ingest ──► Place[] ──► Trained ranker ──► ranked candidates
                       (cached)   (+ confidence)   (ML: LTR)          │
                                                              ▼
                                    Travel matrix ──►  Optimizer (TOPTW)
                                    Opening hours ──►       │
                                    Budget/pace   ──►       ▼
                                                        Itinerary
                                                            │
                                       LLM explanations ────┤
                                                            ▼
                                                      Frontend  ◄──┐
                                                            │      │
                                            user edits / feedback ─┘
                                                            │
                                                    re-optimize affected days
```

- **Ingest is on demand.** We do not pre-build a world database. The user names a destination,
  we fetch that city's data, we cache it. This is what makes the app work anywhere without a
  global data pipeline.
- **Confidence is carried through the whole system.** Every place's hours and cost are tagged
  `known` / `inferred` / `unknown`. The optimizer treats `known` as a hard constraint and
  `inferred` as a soft one. The UI surfaces this to the user. Where the data is thin, the
  system says so instead of pretending.

---

## Repo layout

```
/contracts     JSON schemas. The source of truth. Changes require team agreement.
/fixtures      Hand-made sample data. Everyone develops against this until ingest works. 
/ingest        City data pipeline: Overpass/OSM, enrichment, caching.
/optimizer     Scoring and scheduling.                                      
/ai            LLM layer: extraction, edit parsing, explanations.         
/api           FastAPI service, trip/traveller state, persistence.          
/web           React frontend.                                              
/docs          Design notes, spike results, decisions.
```

Each team works in their own folder. Cross-folder changes get discussed first.

---

## Data contracts

These three shapes are how the whole team stays unblocked. Everyone codes against these, not
against each other's implementations. The authoritative versions are the JSON Schemas in
`/contracts`; the examples below show the shape.

### Place

```json
{
  "id": "osm:node/123456",
  "name": "Museu Nacional do Azulejo",
  "lat": 38.7247,
  "lon": -9.1139,
  "categories": ["museum", "history", "art"],
  "typical_duration_minutes": 90,
  "cost": { "amount": 5.0, "currency": "EUR", "confidence": "known" },
  "hours": {
    "mon": null,
    "tue": [["10:00", "18:00"]],
    "wed": [["10:00", "18:00"]],
    "thu": [["10:00", "18:00"]],
    "fri": [["10:00", "18:00"]],
    "sat": [["10:00", "18:00"]],
    "sun": [["10:00", "18:00"]],
    "confidence": "known"
  },
  "rating": 4.5,
  "popularity": 0.7,
  "source": "osm",
  "last_verified": "2026-09-14"
}
```

- `confidence`: `"known"` (from real data) | `"inferred"` (category default) | `"unknown"`
- `hours.<day>`: `null` means closed. A list of `[open, close]` pairs handles split hours.
- `categories`: tags from the controlled vocabulary in `/contracts/categories.json`. Map
  source taxonomies onto it.

### TravelerProfile

```json
{
  "id": "uuid",
  "interests": {
    "food": 0.9, "history": 0.8, "art": 0.6, "architecture": 0.7,
    "nature": 0.5, "nightlife": 0.2, "shopping": 0.1
  },
  "pace": 0.4,
  "max_walk_minutes": 20,
  "daily_active_hours": 8,
  "day_start": "09:30",
  "day_end": "22:00",
  "budget": { "total": 1200, "currency": "EUR" },
  "dietary": ["vegetarian"],
  "accessibility": [],
  "avoid": [],
  "novelty_appetite": 0.3,
  "feedback": { "accepted": [], "rejected": [] }
}
```

- `interests`: weights 0–1 over the controlled category vocabulary.
- `pace`: 0 = relaxed, 1 = packed. Drives how many items per day.
- `max_walk_minutes`: tolerance *between consecutive stops*, not per day.
- `novelty_appetite`: exploration vs exploitation knob for the scorer.
- `feedback`: place IDs the user accepted/rejected. Drives preference learning.

### Itinerary

```json
{
  "trip_id": "uuid",
  "destination": { "name": "Lisbon", "country": "PT", "lat": 38.72, "lon": -9.14 },
  "start_date": "2026-10-01",
  "end_date": "2026-10-05",
  "days": [
    {
      "date": "2026-10-01",
      "items": [
        {
          "place_id": "osm:node/123456",
          "start": "10:00",
          "end": "11:30",
          "travel_from_prev": { "minutes": 12, "mode": "walk" },
          "cost": 5.0,
          "reason": "Matches your interest in history and it is a 12 minute walk from your morning stop.",
          "confidence": "known"
        }
      ]
    }
  ],
  "totals": { "cost": 240.0, "currency": "EUR", "walking_minutes": 180 },
  "warnings": ["Opening hours for 2 places could not be verified."],
  "score": 0.82
}
```

**Rule: any component may be replaced at any time, as long as it still speaks these shapes.**
That is the entire point.

---

## Machine learning: the trained recommender

The scorer is not hand-coded: it is a model we **train**. This is the project's ML core and
the source of its evaluation story.

- **Task:** learning-to-rank. Given a traveler + context, rank candidate places by predicted
  fit. It implements `score(place, profile, context) -> float`, a drop-in for the earlier
  hand-coded stub, so nothing downstream changes.
- **Model:** LightGBM with the LambdaRank objective (gradient-boosted trees). CPU-trainable in
  minutes, strong, and it yields feature importances we reuse for explanations. A neural
  two-tower ranker (PyTorch) is an optional stretch comparison later.
- **Features (content-based, so the model transfers to any city):** interest–category match,
  price-fit vs budget, popularity, rating, novelty, travel friction, opening-hours
  feasibility, and context (time left, weather).
- **Data:** start with a synthetic generator (the whole train/eval loop runs with zero external
  deps), then anchor on a real public dataset (e.g. the Yelp Open Dataset) for credibility. We
  learn feature→relevance weights that generalize, rather than memorizing place IDs.
- **Evaluation (this is the technical paper's result):** NDCG@k, Precision@k, MAP on held-out
  data, compared against baselines: random, popularity, the old hand-coded scorer, and an
  LLM-as-recommender. It answers the question: *is our trained recommender actually better?*
- **Artifacts:** the trained model is small; commit it under `models/` with `train.py`,
  `evaluate.py`, and `docs/model-card.md`.

The one rule still holds: the trained model **ranks**, deterministic code **schedules**, the
LLM only does language.

---

## Stack

- **Python 3.11** — ingest, optimizer, ai, api
- **FastAPI** — the API service
- **React + TypeScript + Vite** — web
- **SQLite** to start, Postgres if we outgrow it
- **LightGBM / scikit-learn** — the trained learning-to-rank recommender; optional **PyTorch** for a neural stretch model
- **Ollama** + an 8B-class local model for the LLM layer
- **pytest** for Python, **vitest** for web

---

## Team and ownership

| Area | People | Owns |
|---|---|---|
| Lead / Backend | 1 | API, trip + traveller state, persistence, re-optimization, **keeping main green** |
| Data | 2 | Ingest, enrichment, confidence tagging, caching, travel matrices, **+ the training-data pipeline** (features, labels, train/test splits) |
| Model & Ranking | 2 | **Train + evaluate the learning-to-rank recommender**, feature engineering, integrate it as the scorer; the deterministic scheduler + re-optimization logic |
| AI | 1 | Preference extraction, edit parsing, explanation generation, model abstraction |
| Frontend | 1 | Form flow, itinerary view, map, conversational editing UI |

---

## Roadmap

The dated sprint schedule and per-person tasks live on the project wiki. The engineering arc:

1. **Skeleton + spikes** — something runs end to end; resolve the three unknowns (data
   coverage, local-LLM reliability, cheap-vs-real routing), each producing a number in `/docs`.
2. **Real components** — each team swaps its fake for a real one; genuine end-to-end on 2–3
   cities.
3. **Differentiators** — feedback/preference learning, conversational editing, confidence
   display, explanations.
4. **Harden & ship** — bugs, latency, edge cases; rehearse the demo; write the scaling analysis.

---

## Working agreements

- **Main always runs.** If a merge breaks the skeleton, it gets reverted,
  not debugged on main.
- **Weekly integration checkpoint.** Everyone merges.
- **Contracts change by agreement.** Editing `/contracts` unilaterally breaks other people's
  work silently.
- **Every spike produces a written number in `/docs`.**
- **Branch per issue, PR into main.** Small PRs. See `CONTRIBUTING.md`.

---

## Non-goals

Explicitly out of scope. Do not build these, do not design for them:

- Destination recommendation ("where should I go?") — we start once the user names a place
- Flight, hotel, or restaurant *booking*: we recommend, we don't transact
- Collaborative filtering — we have no user base to learn from. Personalization is
  content-based plus feedback
- Native mobile apps
- Multi-city trips in one itinerary
- User accounts and auth beyond whatever the demo needs
