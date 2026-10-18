# Data pipeline: design notes and decisions

Owner: Data team. How to run it lives in [`ingest/README.md`](../ingest/README.md). This page
records why it works the way it does, so the next person does not undo a decision by accident.

## Decisions

**1. OpenStreetMap only, through Overpass, no paid API.**
Zero budget is a project constraint. OSM has the places, coordinates and a fair share of
opening hours. It has no review scores and patchy prices, which the confidence labels and
the curation step deal with.

**2. One curated snapshot city for the demo (Rome), any other city on demand.**
The brief says it plainly: pick one city, snapshot the data once, hand curate the gaps.
`data/cities/rome/` is committed, so the demo never waits on Overpass (a full city fetch
takes minutes and Overpass rate limits hard). Other cities still work through
`make ingest`, with raw OSM coverage only.

**3. The catalog decides where a city comes from, not the API.**
`ingest/catalog.py` resolves a destination name to a committed snapshot or the Lisbon
fixtures. The API and the optimizer call `load_city()` and never touch file paths. Local
runs in `data/out` are only served when `WANDERWISE_EXTRA_CITIES` says so, so a spike run on
one laptop cannot change what the API or the ranker sees. An unknown city raises
`CityNotAvailable`, and the API turns that into a 422 that names the cities that do work.
This fixes the Sprint 1 integration finding where New York returned Lisbon places.

**4. Strict parsing, honest labels.**
`known` means the value came from real data or from a person checking the official source.
A value we half understood is `unknown`, not a guess labelled as a fact. The optimizer treats
`known` hours as a hard constraint, so one wrong `known` costs more than ten `unknown`s.

**5. The most specific tag decides the primary category.**
The primary category picks default hours, default visit length and whether entry is assumed
free. A bar tagged `tourism=attraction` stays a bar first (bar hours, not open all day and
free), and gets `landmark` only as a second category. Order: venues, typed sights, green
spaces, then neighborhood and landmark.

**6. Popularity is a proxy and says so.**
No visitor counts exist in OSM. Translated names, Wikidata and Wikipedia links and heritage
status track fame closely: the Colosseum has well over a hundred name translations, a corner
cafe has none. The score is used to order candidates and break ties, never shown as a fact.

**7. Duplicates are merged before anything is ranked.**
OSM maps many sights twice (an entrance node plus a building polygon). Without the merge the
optimizer could schedule the same church twice on one day.

**8. A big ticketed site is one stop.**
OSM maps each temple of the Roman Forum and each gallery of the Vatican Museums as its own
sight, with default hours of open all day and free. Scheduled on their own, the planner would
send someone to the Temple of Saturn at 9 pm. The curation file draws a polygon around such
sites and keeps only the main entry, which carries the real hours, ticket and visit length.

**9. Travel times are computed, not called.**
Walking time is straight line distance times a detour factor. The routing spike
([`routing-spike.md`](routing-spike.md)) measured it against OSRM foot routing on 600 pairs of
popular Rome places: a mean error of about 2 minutes per walkable leg, p95 under 6 minutes,
with a small overestimate that works as a buffer. Transit is a flat estimate. Both run in
process in milliseconds, so there is no network call on the request path and no latency risk
in the demo.

## Data dictionary: where each Place field comes from

| Field | Source | Notes |
|-------|--------|-------|
| `id` | `osm:<type>/<id>` | stable as long as the OSM object exists |
| `name` | `name` tag | records without a name are dropped |
| `lat`, `lon` | node position, or the centre of a way or relation | |
| `categories` | tag mapping in `categories.py` | first entry is the primary category |
| `typical_duration_minutes` | category default, or curated | largest default among the categories |
| `cost` | `fee` and `charge` tags, or curated | currency from the charge, else the country default |
| `hours` | `opening_hours` tag, or curated | category default (`inferred`) when the tag is missing |
| `popularity` | tag signals, see decision 6 | 0..1, three decimals |
| `rating` | never set | OSM has no reviews |
| `source` | `osm`, or `osm+curated` when a person checked it | |
| `last_verified` | date of the Overpass fetch, or the curation check date | |

## Popularity formula

```
popularity = 0.45 * min(1, log(1 + translated_names) / log(1 + 40))
           + 0.15 * has_wikidata + 0.15 * has_wikipedia + 0.10 * has_heritage
           + 0.10 * is_tourism_sight + 0.05 * documentation_tags / 9
```

Weights add up to 1. Forty translated names (or more) earn the full name weight.

## Travel model numbers

| Parameter | Value | Why |
|-----------|-------|-----|
| walking speed | 4.5 km/h | relaxed tourist pace with stops |
| walking detour factor | 1.3 | street distance over straight line; the routing spike measured a median of 1.225 in Rome, and 1.3 is kept as a one minute buffer per leg |
| transit overhead | 10 min | walk to the stop and wait |
| transit speed | 15 km/h | bus and metro average in a historic centre |
| transit detour | 1.4 | routes are less direct than streets |

## What is still open

- The JSON shape of `matrix.json` is a proposal. The optimizer reads `travel_legs()` output
  directly, which needs no file at all.
- Training data for the ranker on real places: the Rome snapshot gives real candidates, but
  real relevance labels still need a public dataset (Sprint 2 plan). Real places never carry
  `rating`, so a model trained on synthetic ratings should be retrained before it ranks them.
- About 2% of OSM `opening_hours` values stay `unknown` because the parser does not read
  month ranges, extended times such as `19:00-26:00`, or rules joined by a comma. Supporting
  them is a parser change worth doing once the demo city is settled.
- Day trips (Ostia Antica, Tivoli) need curated entries; OSM cannot say what a day trip is.
