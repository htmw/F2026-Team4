# Data spike: OSM coverage of hours and prices

Generated 2026-10-18 by `python -m ingest.spike`. Raw OSM only, no manual curation.

- **Real hours**: `opening_hours` present and fully parsed (confidence `known`).
- **Unparseable**: tag present but outside the supported subset (confidence `unknown`).
- **No hours tag**: category default used (confidence `inferred`).
- **Real price**: `charge` parsed to one amount (`known`, > 0).
- **Known free**: `fee=no` (`known`).
- **Assumed free**: no fee tag on a usually free category such as a park or a church (`inferred`).

## Summary

| City | Status | Places | Real hours | Unparseable | No hours tag | Real price | Known free | Assumed free | No price data |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Lisbon, Portugal | OK | 6073 | 25.0% | 2.5% | 72.5% | 0.5% | 0.4% | 19.5% | 79.6% |

## The 100 most popular sights per city

Food and drink left out. These are the places an itinerary is built around, so this is the coverage that matters most.

| City | Sights | Real hours | Real price or known free |
|---|---:|---:|---:|
| Lisbon, Portugal | 100 | 29.0% | 16.0% |

## Lisbon, Portugal

| Primary category | Places | Real hours | Real price or known free |
|---|---|---|---|
| restaurant | 2827 | 29.8% | 0.0% |
| cafe | 1155 | 31.6% | 0.0% |
| bar | 367 | 26.2% | 0.0% |
| landmark | 276 | 8.3% | 0.4% |
| church | 251 | 2.8% | 0.0% |
| park | 228 | 7.0% | 1.8% |
| shop | 194 | 20.1% | 0.0% |
| palace | 150 | 1.3% | 0.0% |
| bakery | 139 | 36.7% | 0.0% |
| garden | 119 | 4.2% | 2.5% |
| museum | 104 | 37.5% | 41.3% |
| gallery | 59 | 16.9% | 3.4% |
| viewpoint | 53 | 1.9% | 1.9% |
| market | 47 | 27.7% | 0.0% |
| castle | 36 | 2.8% | 2.8% |
| nightclub | 31 | 22.6% | 0.0% |
| neighborhood | 27 | 0.0% | 0.0% |
| monument | 10 | 0.0% | 0.0% |

Dropped: always_closed=3, no_position=2, outside_bbox=8, unmapped_category=460

Duplicate records merged: 127

Area (geocoded bbox, S,W,N,E): 38.6914, -9.2298, 38.7968, -9.0863

## Reading these numbers

- Coverage differs by category (museums vs. restaurants),
  so compare the per-category tables.
- `typical_duration_minutes` is always a category default (the contract has no confidence field for it).
- Holiday (`PH`/`SH`) opening rules are ignored; the contract has no holiday field.

## What this means

- Real opening hours exist for 25% of places. The optimizer has to plan most stops on `inferred` hours, as a soft constraint, and the UI has to say so.
- A known price (paid or free) exists for 0.9% of places. OSM is not a price source; budget totals rest on curation and category assumptions.
- Among the 100 most popular sights, 29% have real hours. Hand curating the top sights of the demo city closes the gap where it matters, which is what the curation step in data/curation/ is for.
- Recommendation: for the MVP, curate the top sights of the demo city instead of wiring in a commercial places API. Revisit a free tier (restaurant hours and ratings) only when more cities are needed.
