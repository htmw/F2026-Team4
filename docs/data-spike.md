# Data spike: OSM coverage of hours and prices

Generated 2026-10-17 by `python -m ingest.spike`. Raw OSM only, no manual curation.

- **Real hours**: `opening_hours` present and fully parsed (confidence `known`).
- **Unparseable**: tag present but outside the supported subset (confidence `unknown`).
- **No hours tag**: category default used (confidence `inferred`).
- **Real price**: `charge` parsed to one amount (`known`, > 0).
- **Known free**: `fee=no` (`known`).
- **Assumed free**: no fee tag on a usually free category such as a park or a church (`inferred`).

## Summary

| City | Status | Places | Real hours | Unparseable | No hours tag | Real price | Known free | Assumed free | No price data |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Rome, Italy | OK | 4753 | 21.1% | 2.4% | 76.5% | 0.2% | 0.8% | 27.5% | 71.4% |
| Lisbon, Portugal | OK | 6085 | 24.9% | 2.5% | 72.6% | 0.5% | 0.4% | 19.7% | 79.4% |
| Porto, Portugal | OK | 3062 | 21.8% | 2.0% | 76.2% | 1.1% | 1.3% | 26.2% | 71.3% |
| Tbilisi, Georgia | OK | 2524 | 27.5% | 0.8% | 71.7% | 0.1% | 0.3% | 23.2% | 76.4% |

## The 100 most popular sights per city

Food and drink left out. These are the places an itinerary is built around, so this is the coverage that matters most.

| City | Sights | Real hours | Real price or known free |
|---|---:|---:|---:|
| Rome, Italy | 100 | 29.0% | 5.0% |
| Lisbon, Portugal | 100 | 29.0% | 16.0% |
| Porto, Portugal | 100 | 30.0% | 21.0% |
| Tbilisi, Georgia | 100 | 16.0% | 3.0% |

## Rome, Italy

| Primary category | Places | Real hours | Real price or known free |
|---|---|---|---|
| restaurant | 1967 | 29.7% | 0.0% |
| cafe | 880 | 16.9% | 0.0% |
| landmark | 502 | 2.0% | 0.8% |
| church | 392 | 14.0% | 0.0% |
| bar | 303 | 29.4% | 0.0% |
| park | 150 | 4.7% | 1.3% |
| museum | 134 | 27.6% | 28.4% |
| shop | 105 | 13.3% | 0.0% |
| bakery | 93 | 34.4% | 0.0% |
| garden | 51 | 3.9% | 7.8% |
| monument | 45 | 0.0% | 0.0% |
| market | 34 | 41.2% | 0.0% |
| neighborhood | 26 | 0.0% | 0.0% |
| nightclub | 23 | 13.0% | 0.0% |
| viewpoint | 22 | 4.5% | 0.0% |
| gallery | 18 | 16.7% | 0.0% |
| castle | 4 | 25.0% | 25.0% |
| palace | 4 | 25.0% | 0.0% |

Dropped: always_closed=10, unmapped_category=492

Duplicate records merged: 111

Area (explicit bbox, S,W,N,E): 41.8700, 12.4300, 41.9400, 12.5300

## Lisbon, Portugal

| Primary category | Places | Real hours | Real price or known free |
|---|---|---|---|
| restaurant | 2826 | 29.8% | 0.0% |
| cafe | 1155 | 31.6% | 0.0% |
| bar | 367 | 26.2% | 0.0% |
| landmark | 282 | 7.8% | 0.4% |
| church | 252 | 2.8% | 0.0% |
| park | 233 | 7.3% | 1.7% |
| shop | 194 | 20.1% | 0.0% |
| palace | 149 | 1.3% | 0.0% |
| bakery | 139 | 36.7% | 0.0% |
| garden | 119 | 4.2% | 2.5% |
| museum | 104 | 37.5% | 41.3% |
| gallery | 59 | 16.9% | 3.4% |
| viewpoint | 54 | 1.9% | 1.9% |
| market | 47 | 27.7% | 0.0% |
| castle | 36 | 2.8% | 2.8% |
| nightclub | 31 | 22.6% | 0.0% |
| neighborhood | 27 | 0.0% | 0.0% |
| monument | 10 | 0.0% | 0.0% |
| beach | 1 | 0.0% | 0.0% |

Dropped: always_closed=4, unmapped_category=460

Duplicate records merged: 124

Area (geocoded bbox, S,W,N,E): 38.6914, -9.2298, 38.7968, -9.0863

## Porto, Portugal

| Primary category | Places | Real hours | Real price or known free |
|---|---|---|---|
| restaurant | 1102 | 25.9% | 0.0% |
| cafe | 647 | 25.2% | 0.0% |
| church | 205 | 5.4% | 2.4% |
| bar | 201 | 28.4% | 0.5% |
| landmark | 197 | 4.1% | 3.6% |
| shop | 161 | 14.3% | 0.0% |
| bakery | 86 | 34.9% | 0.0% |
| garden | 86 | 4.7% | 2.3% |
| park | 78 | 19.2% | 3.8% |
| museum | 73 | 46.6% | 60.3% |
| gallery | 46 | 23.9% | 28.3% |
| castle | 31 | 3.2% | 0.0% |
| nightclub | 30 | 13.3% | 0.0% |
| neighborhood | 28 | 0.0% | 0.0% |
| market | 27 | 74.1% | 0.0% |
| viewpoint | 22 | 0.0% | 4.5% |
| monument | 15 | 0.0% | 0.0% |
| beach | 14 | 0.0% | 0.0% |
| palace | 13 | 7.7% | 0.0% |

Dropped: always_closed=4, unmapped_category=184

Duplicate records merged: 64

Area (geocoded bbox, S,W,N,E): 41.1384, -8.6913, 41.1859, -8.5521

## Tbilisi, Georgia

| Primary category | Places | Real hours | Real price or known free |
|---|---|---|---|
| cafe | 705 | 41.3% | 0.0% |
| restaurant | 672 | 30.1% | 0.0% |
| bar | 265 | 34.0% | 0.0% |
| church | 197 | 3.6% | 0.0% |
| bakery | 183 | 19.1% | 0.0% |
| landmark | 118 | 2.5% | 0.8% |
| park | 89 | 9.0% | 0.0% |
| shop | 85 | 23.5% | 0.0% |
| neighborhood | 52 | 0.0% | 0.0% |
| museum | 42 | 40.5% | 7.1% |
| nightclub | 28 | 21.4% | 0.0% |
| gallery | 28 | 32.1% | 3.6% |
| market | 27 | 11.1% | 0.0% |
| garden | 11 | 18.2% | 45.5% |
| monument | 9 | 0.0% | 0.0% |
| castle | 5 | 0.0% | 0.0% |
| viewpoint | 4 | 0.0% | 0.0% |
| palace | 2 | 50.0% | 0.0% |
| beach | 2 | 0.0% | 0.0% |

Dropped: unmapped_category=902

Duplicate records merged: 40

Area (geocoded bbox, S,W,N,E): 41.6178, 44.5962, 41.8439, 45.0173

## Reading these numbers

- Coverage differs by category (museums vs. restaurants),
  so compare the per-category tables.
- `typical_duration_minutes` is always a category default (the contract has no confidence field for it).
- Holiday (`PH`/`SH`) opening rules are ignored; the contract has no holiday field.

## What this means

- Real opening hours exist for 21 to 27% of places. The optimizer has to plan most stops on `inferred` hours, as a soft constraint, and the UI has to say so.
- A known price (paid or free) exists for 0.4 to 2.5% of places. OSM is not a price source; budget totals rest on curation and category assumptions.
- Among the 100 most popular sights, 16 to 30% have real hours. Hand curating the top sights of the demo city closes the gap where it matters, which is what data/curation/ does.
- Recommendation: for the MVP, curate the top sights of the demo city instead of wiring in a commercial places API. Revisit a free tier (restaurant hours and ratings) only when more cities are needed.
