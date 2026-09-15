# Personalized Multi-Agent Travel Recommender (CS-691)

A personalized travel itinerary planner. The user says where they're going, how long they
have, and what they care about: the system produces a day-by-day schedule that is **actually
executable**: real opening hours, real travel times, real costs, and it also lets the user modify it
in natural language.

**The one rule:** the language model does not plan the trip, an optimizer does. The LLM only
turns text into structured data and explains decisions the optimizer already made. See
[`DESIGN.md`](DESIGN.md) for the full architecture and data contracts. The team plan, roles,
and sprint calendar live on the project wiki.

## What runs today (the walking skeleton)
Fill a preference form → submit → see a day-by-day itinerary. It's intentionally naive (the
scheduler ignores travel time and opening hours) so every team has a working end-to-end path
and a clear place to plug in real work.

```
Preference form ─► TravelerProfile ─┐
                                     ▼
        fixtures/ places ─► score ─► greedy pack ─► Itinerary ─► itinerary view
                                     ▲
                     (Optimizer team replaces this stub)
```

## Quick start
```bash
make install     # Python deps (uv, Python 3.11) + web deps (npm)
make test        # run all tests
make run-api     # API on http://localhost:8000  (docs at /docs)
make run-web     # in a second terminal: frontend on http://localhost:5173
```
Then open the frontend, fill the form, and submit.

## Layout
| Folder | What |
|--------|------|
| [`contracts/`](contracts) | JSON Schemas — the source of truth (Place, TravelerProfile, Itinerary)|
| [`fixtures/`](fixtures) | Hand-made sample data everyone develops against|
| [`ingest/`](ingest) | City data pipeline (OSM, enrichment, caching, travel matrix)|
| [`optimizer/`](optimizer) | Scoring + scheduling — the graded core|
| [`ai/`](ai) | LLM layer: extraction, edit parsing, explanations|
| [`api/`](api) | FastAPI orchestrator, trip/traveler state, the stub scheduler|
| [`web/`](web) | React + TypeScript frontend|
| [`docs/`](docs) | Design notes, spike results|

## Requirements
- Python 3.11 (managed by [uv](https://docs.astral.sh/uv/))
- Node 20+ / npm
- (Later, for the AI layer) [Ollama](https://ollama.com) with a local 8B-class model

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the branch/PR/CI workflow.
