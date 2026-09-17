# Routing spike (Optimizer + Data) — fill in a NUMBER

**Question:** How far off is `haversine × factor` from real OSRM walking times? Is the cheap
version good enough to schedule with?

Sample N place-pairs, compare estimated vs real walking minutes, fill this in.

| Method | Mean abs error (min) | p95 error (min) | Good enough? |
|--------|---------------------:|----------------:|--------------|
| haversine × 1.3 | | | |
| OSRM walking | (reference) | (reference) | — |

**Decision this informs:** whether the optimizer can use a cheap distance estimate or must
call a real routing service (and pay the latency cost) for feasibility.
