# Data spike (Data team)

**Question:** For tourist-relevant POIs, what fraction have real `opening_hours`? Real prices?

We ran the ingestion for Lisbon, Porto, and Tbilisi and checked the reports generated for each city.

| City | POIs found | % with real hours | % with real price | Notes |
|------|-----------:|------------------:|------------------:|-------|
| Lisbon | 6097 | 25.2% | 0.54% | 1536 hours parsed; 33 numeric prices |
| Porto | 2991 | 21.2% | 1.24% | 635 hours parsed; 37 numeric prices |
| Tbilisi | 2378 | 29.2% | 0.13% | 694 hours parsed; 3 numeric prices |

**Observation:** The reports show that opening hours and numeric prices are missing for many places. The current results include restaurants, cafes, shops, and attractions, so they are not limited to tourist attractions.

**Decision this informs:** Wanderwise needs to handle missing information and distinguish actual data from inferred data. We can also use these results to decide whether another data source would help.
