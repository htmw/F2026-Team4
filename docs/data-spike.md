# Data spike: OSM coverage of opening hours and prices in Lisbon, Portugal

Generated 2026-10-18 by `python -m ingest.spike` (`make data-spike`). Raw OpenStreetMap data only, without the hand checked curation file.

## Summary

| What | Places | Share |
|---|---:|---:|
| All places | 6073 | 100.0% |
| Real hours: opening_hours tag fully read (`known`) | 1518 | 25.0% |
| Hours tag we cannot read (`unknown`) | 153 | 2.5% |
| No hours tag: category default used (`inferred`) | 4402 | 72.5% |
| Real price: a charge tag with one amount (`known`) | 33 | 0.5% |
| Known free: fee=no (`known`) | 22 | 0.4% |
| Assumed free: no fee tag on a usually free category (`inferred`) | 1181 | 19.4% |
| No price data (`unknown`) | 4837 | 79.6% |

## The 100 most popular sights

Food and drink left out. An itinerary is built around these places, so this is the coverage that matters most.

- Real hours: 29 of 100 (29.0%)
- Real price or known free: 16 of 100 (16.0%)

## By primary category

| Primary category | Places | Real hours | Real price or known free |
|---|---:|---:|---:|
| restaurant | 2827 | 29.8% | 0.0% |
| cafe | 1155 | 31.6% | 0.0% |
| bar | 367 | 26.2% | 0.0% |
| landmark | 275 | 8.4% | 0.4% |
| church | 251 | 2.8% | 0.0% |
| park | 228 | 7.0% | 1.8% |
| shop | 194 | 20.1% | 0.0% |
| palace | 151 | 1.3% | 0.0% |
| bakery | 139 | 36.7% | 0.0% |
| garden | 118 | 4.2% | 2.5% |
| museum | 105 | 37.1% | 41.0% |
| gallery | 59 | 16.9% | 3.4% |
| viewpoint | 53 | 1.9% | 1.9% |
| market | 47 | 27.7% | 0.0% |
| castle | 36 | 2.8% | 2.8% |
| nightclub | 31 | 22.6% | 0.0% |
| neighborhood | 27 | 0.0% | 0.0% |
| monument | 10 | 0.0% | 0.0% |

Dropped records: always_closed=3, no_position=2, outside_bbox=8, unmapped_category=460. Duplicate records merged: 127. Area searched (south, west, north, east): 38.6914, -9.2298, 38.7968, -9.0863.

## What this means

- Real opening hours exist for 25.0% of places. The optimizer has to plan most stops on `inferred` hours, as a soft constraint, and the app has to say so.
- A known price (paid or free) exists for 0.9% of places. OpenStreetMap is not a price source, so budget totals rest on the curation file and on category defaults.
- Among the 100 most popular sights, 29.0% have real hours. Hand checking those sights on their official websites, in a curation file (data/curation/lisbon.json, not written yet), closes the gap where it matters most.
- `typical_duration_minutes` is always a category default unless a curated entry sets it. Holiday rules (PH, SH) are skipped because the contract has no holiday field.
