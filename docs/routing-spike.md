# Routing spike: is haversine x factor good enough to schedule with?

Generated 2026-10-18 by `python -m ingest.routing_spike`. City: Lisbon. Reference: https://routing.openstreetmap.de/routed-foot (OSRM, foot profile).

Sample: 600 ordered pairs between popular places, 168 of them walkable (at most 45 minutes on real streets at 4.5 km/h). Median straight line distance 4.74 km, longest 13.59 km.

## Answer

Errors on walkable legs, in minutes, against the real street distance walked at our planning speed:

| Method | Mean abs error (min) | p95 error (min) | Bias (min) | Good enough? |
|--------|---------------------:|----------------:|-----------:|--------------|
| haversine x 1.3 | 1.83 | 5.27 | +0.68 | Yes |
| haversine x 1.230 (sample median) | 1.88 | 4.59 | -0.65 | Yes |
| OSRM walking | (reference) | (reference) | (reference) | n/a |

Good enough means a mean error of at most 3 minutes and a p95 of at most 8 minutes per leg. A positive bias means we overestimate.

## Detour ratio (street distance / straight line)

Median 1.23, mean 1.244, 10th percentile 1.121, 90th percentile 1.351.

## All pairs against OSRM durations

The OSRM foot profile walks at about 4.48 km/h, the same as the 4.5 km/h we plan with, so the gap below is geometry only.
Long legs are included here, which is why the errors grow; past the walking tolerance those legs go by transit anyway.

| Method | Mean abs error (min) | p95 error (min) | Bias (min) |
|--------|---------------------:|----------------:|-----------:|
| haversine x 1.3 | 5.76 | 19.16 | +4.59 |
| haversine x 1.230 (sample median) | 4.38 | 11.63 | +0.06 |

## Decision

The cheap estimate is good enough for scheduling. The optimizer keeps the in-process matrix: no routing call on the request path, so no latency cost in the demo.

Keep haversine x 1.3. It passes, and it overestimates a walkable leg by about 0.7 minutes on average, a small buffer for finding the way. The measured median factor (1.23) is a little tighter but leaves no slack.

Real routing stays useful for one final check of a finished itinerary.
