# Routing spike: is haversine x factor good enough to schedule with?

Generated 2026-10-17 by `python -m ingest.routing_spike`. City: Rome. Reference: https://routing.openstreetmap.de/routed-foot (OSRM, foot profile).

Sample: 600 ordered pairs between popular places, 436 of them walkable (at most 45 minutes on real streets at 4.5 km/h). Median straight line distance 1.95 km, longest 7.46 km.

## Answer

Errors on walkable legs, in minutes, against the real street distance walked at our planning speed:

| Method | Mean abs error (min) | p95 error (min) | Bias (min) | Good enough? |
|--------|---------------------:|----------------:|-----------:|--------------|
| haversine x 1.3 | 2.13 | 5.71 | +1.06 | Yes |
| haversine x 1.225 (sample median) | 1.49 | 5.11 | -0.46 | Yes |
| OSRM walking | (reference) | (reference) | (reference) | n/a |

Good enough means a mean error of at most 3 minutes and a p95 of at most 8 minutes per leg. A positive bias means we overestimate.

## Detour ratio (street distance / straight line)

Median 1.225, mean 1.264, 10th percentile 1.118, 90th percentile 1.4.

## All pairs against OSRM durations

The OSRM foot profile walks at about 4.5 km/h, the same as the 4.5 km/h we plan with, so the gap below is geometry only.
Long legs are included here, which is why the errors grow; past the walking tolerance those legs go by transit anyway.

| Method | Mean abs error (min) | p95 error (min) | Bias (min) |
|--------|---------------------:|----------------:|-----------:|
| haversine x 1.3 | 3.47 | 11.77 | +2.65 |
| haversine x 1.225 (sample median) | 2.19 | 7.54 | +0.47 |

## Decision

The cheap estimate is good enough for scheduling. The optimizer keeps the in-process matrix: no routing call on the request path, so no latency cost in the demo.

Keep haversine x 1.3. It passes, and it overestimates a walkable leg by about 1.1 minutes on average, a small buffer for finding the way. The measured median factor (1.225) is a little tighter but leaves no slack.

Real routing stays useful for one final check of a finished itinerary.
