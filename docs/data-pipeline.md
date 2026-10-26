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
runs in `data/out` are only served when `WANDERWISE_EXTRA_CITIES` says so, and only for
cities with no committed data, so a spike run on one laptop cannot change what the API or
the ranker sees for Rome or Lisbon. An unknown city, a missing name, or "Rome, Georgia"
raises `CityNotAvailable`, and the API turns that into a 422 that names the cities that do
work. This fixes the Sprint 1 integration finding where New York returned Lisbon places.

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
optimizer could schedule the same church twice on one day. Groups form around the richest
record and every distance is measured to it. An earlier version linked any two close
records, and a row of neighbours could chain into one group across a whole district.
City walls and aqueducts are the opposite case: OSM splits them into dozens of pieces with
one name (91 for the Aurelian Walls), so every piece of one structure becomes one stop.

**8. A big ticketed site is one stop.**
OSM maps each temple of the Roman Forum and each gallery of the Vatican Museums as its own
sight, with default hours of open all day and free. Scheduled on their own, the planner would
send someone to the Temple of Saturn at 9 pm. The curation file draws a polygon around such
sites and keeps only the main entry, which carries the real hours, ticket and visit length.
A polygon never removes a neighbourhood (the label point of the Campitelli district sits
inside the Forum polygon). Other records of a curated sight, such as the Ara Pacis altar
next to its museum, are folded into the curated record, so they cannot come back as a free
stop with guessed hours.

**9. Travel times are computed, not called.**
Walking time is straight line distance times a detour factor. The routing spike
([`routing-spike.md`](routing-spike.md)) measured it against OSRM foot routing on 600 pairs of
popular Rome places: a mean error of about 2 minutes per walkable leg, p95 under 6 minutes,
with a small overestimate that works as a buffer. Transit is a flat estimate. Both run in
process (about 0.1 s for all pairs of 300 candidates), so there is no network call on the
request path and no latency risk in the demo.

**10. A position must be a real point.**
Overpass gives a way or a relation the centre of its bounding box. For a ring of walls that
centre is the middle of the city: the Aurelian Walls relation sat next to the Colosseum. A
wall or aqueduct is therefore placed on one of its pieces, never on a relation that only
groups parts (type site, route, building or waterway). A place whose centre falls outside
the requested bbox is dropped (one aqueduct relation landed 17 km east of Rome).

**11. Any other city is fetched live, on the first request.**
The design says ingest is on demand, so the catalog no longer stops at Rome and Lisbon. A
city with no committed data is geocoded, fetched and run through the same pipeline while
the traveler waits, then kept in `data/live/` so nobody waits twice. Choices made on the way:
- One combined Overpass query instead of nine, for 5 km around the centre rather than the
  whole admin area, so a big city stays one fetch.
- Settlements only: an open search for "newyork" matched a shop called NEWYORK in Tokyo.
- A country or state is refused by its OpenStreetMap type, and only when it is over 100 km
  across: Delhi and Mexico City are states in OpenStreetMap and Singapore is a country, but
  all three are cities. The old 80 km check on every place would have refused real cities
  whose admin area is large.
- Retries follow what the test runs showed: the main server answers 502 for a moment and is
  fine seconds later. So a live fetch tries it three times, 5 s and 15 s apart, 120 s per try
  (the query's own limit). No mirror is used: in October 2026 every public mirror tried
  either never answered, no longer existed, gave 504 or refused the request.
- A 504 means Overpass gave up on the query itself, so the same query is not sent again.
  The fetch is retried once for 2.5 km instead of 5 km: central London failed this way.
- Prices use the city's own currency (every ISO country is listed), and the itinerary names
  the country, so "Columbia" (South Carolina) is not mistaken for Colombia.
- A saved city is fetched again after 30 days, because places open and close. If
  OpenStreetMap is down at that moment the old copy is served: an older plan beats none.
- No curation for live cities: hours and prices are mostly `inferred`, and each stop says so.

## Data dictionary: where each Place field comes from

| Field | Source | Notes |
|-------|--------|-------|
| `id` | `osm:<type>/<id>` | stable as long as the OSM object exists |
| `name` | `name` tag | records without a name are dropped |
| `lat`, `lon` | node position, or the centre of a way or relation | a wall or aqueduct is placed on its best piece; centres outside the bbox are dropped (decision 10) |
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
- Some OSM `opening_hours` values stay `unknown`: month ranges (`Apr-Oct ...`) on purpose,
  because the contract holds one weekly pattern and the trip's season is not known here,
  plus sunrise/sunset, week numbers and comments. Times past midnight (`19:00-26:00`) and
  rules joined by a comma (`Mo-Fr 09:00-17:00, Sa 10:00-14:00`) are read since October 2026.
- Day trips (Ostia Antica, Tivoli) need curated entries; OSM cannot say what a day trip is.
