# /optimizer — Recommendation + Itinerary (Optimizer team, 2 people)

**You own the graded core:** choosing *which* experiences and *in what order* they form a
good trip.

## Contract boundary
- **In:** a `TravelerProfile` ([`/contracts/traveler-profile.schema.json`](../contracts/traveler-profile.schema.json)),
  a list of `Place` objects, and a travel matrix from the Data team.
- **Out:** an `Itinerary` ([`/contracts/itinerary.schema.json`](../contracts/itinerary.schema.json)).

## What you replace
The naive stub in [`/api/scheduler_stub.py`](../api/scheduler_stub.py). Build real,
**pure functions** (easy to test in isolation):
```
score(place, profile) -> float
schedule(places, profile, dates, travel_matrix) -> Itinerary
```

## Sprint-1 deliverable
- A greedy insertion heuristic that **respects opening hours** (`known` = hard constraint,
  `inferred` = soft with a score penalty), `typical_duration_minutes`, `max_walk_minutes`,
  and the daily time window.
- Tests against [`/fixtures`](../fixtures) — correctness here is not eyeballable, so the test
  is part of the code.
- The **routing spike** number in [`/docs/routing-spike.md`](../docs/routing-spike.md):
  how far off is haversine × factor from real walking times? Is the cheap version good enough?
- Document the algorithm in [`/docs/optimizer.md`](../docs/optimizer.md).

## The one rule
No LLM in the scoring/selection/scheduling path. This is deterministic code. The whole
project exists to prove an optimizer plans better than "ask a model for an itinerary."
