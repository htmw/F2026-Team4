# Data slice: user stories, acceptance criteria and test cases

Owner: Sushma (Data). Every story below is covered by automated tests that run in CI on each
pull request (`make test`). The test file is named in the last column.

## User stories

| ID | As a... | I want... | so that... | Acceptance criteria |
|----|---------|-----------|------------|---------------------|
| DS-1 | traveler | the plan to use real places in the city I typed | the trip is for my destination | A Rome request schedules only Rome places. An unknown city, a request with no city name, or a namesake in another country (Rome, Georgia) gets a 422 that names the cities with data. No silent fallback to Lisbon. |
| DS-2 | traveler | to know which hours and prices are verified | I know what to double check before going | Every place carries `known`, `inferred` or `unknown` on hours and cost. `known` only comes from fully parsed OSM tags or a hand checked official source with a date and URL. |
| DS-3 | optimizer | travel minutes between any two candidates | each day is physically possible | `travel_legs()` returns minutes and mode for every ordered pair. A leg is `walk` only within the traveler's `max_walk_minutes`, otherwise `transit`. No network call. |
| DS-4 | traveler | each sight to appear once | my plan never repeats a place | Around the richest record: same wikidata id within 1 km (100 m when the names differ) or same name within 60 m become one, with no chaining through neighbours. A venue never merges with a sight. Each city wall or aqueduct is one stop placed on one of its pieces. Copies of a curated sight are folded into it. |
| DS-5 | ranker | a popularity value for every place | famous sights rank apart from a corner cafe | Every ingested place has `popularity` in 0..1 built from OSM tag signals, documented as a proxy. |
| DS-6 | data engineer | to ingest any city by name | we can add a city without code changes | `make ingest CITY=...` writes a valid city folder. Raw responses are cached. Large cities work with `--bbox`. Overpass errors and timeouts are never cached as data. |
| DS-7 | team | measured numbers for data coverage and travel time error | design decisions rest on data, not guesses | `docs/data-spike.md` reports hours and price coverage for 4 cities. `docs/routing-spike.md` reports haversine error against OSRM foot routing. |
| DS-8 | traveler | the planner to know about rain and outdoor stops | asking what if it rains can move outdoor stops | Daily forecast for trip dates up to 16 days ahead, `None` further out, cached for 6 hours. `is_outdoor(place)` by primary category. |

## Test cases

| ID | Story | Steps | Expected result | Automated test |
|----|-------|-------|-----------------|----------------|
| TC-D1 | DS-1 | POST `/plan` with destination `{"name": "Rome"}` | 200, every scheduled `place_id` is in `data/cities/rome/places.json`, destination country IT | `api/tests/test_destinations.py` |
| TC-D2 | DS-1 | POST `/plan` with destination `{"name": "New York"}` | 422, message names New York and lists Rome and Lisbon | `api/tests/test_destinations.py` |
| TC-D3 | DS-1 | POST `/plan` with `{"city": "Lisbon"}` (no name key) | 200, places come from the Lisbon fixtures, warning says sample data | `api/tests/test_destinations.py` |
| TC-D4 | DS-2 | Parse weekday hours, an overnight range `22:00-02:00`, then `PH off` | weekday hours `known`, the overnight tail lands on the next day, `PH off` is not `known` (it says nothing about normal days) | `ingest/tests/test_hours.py` |
| TC-D5 | DS-2 | Parse charges `15,000 VND`, `ENTRY 10`, `adult 10 EUR, child 5 EUR` | 15000 VND `known`; ENTRY is not read as Turkish lira; two prices are not `known` | `ingest/tests/test_cost.py` |
| TC-D6 | DS-2 | Apply a curation entry with hours, price and source to a matching place | hours and cost `known`, source `osm+curated`, `last_verified` is the check date | `ingest/tests/test_curation.py` |
| TC-D7 | DS-2 | Load a curation file with unparseable hours or a non ISO currency | load fails with a message naming the entry | `ingest/tests/test_curation.py` |
| TC-D8 | DS-2 | Validate every committed snapshot place against `place.schema.json` | zero errors, no duplicate ids | `ingest/tests/test_catalog.py` |
| TC-D9 | DS-3 | Build legs for three places 1 km apart with `max_walk_minutes=20` | 1 km hop is walk 17.3 min, 2 km hop is transit, 6 legs in total | `ingest/tests/test_matrix.py` |
| TC-D10 | DS-3 | Build legs with `max_walk_minutes=0` | every leg is transit | `ingest/tests/test_matrix.py` |
| TC-D11 | DS-4 | Dedupe a node and a way named the same 30 m apart | one record left, categories merged, known hours kept | `ingest/tests/test_dedupe.py` |
| TC-D12 | DS-4 | Dedupe two bars with the same name 500 m apart | both kept | `ingest/tests/test_dedupe.py` |
| TC-D13 | DS-5 | Score a famous sight and a plain cafe | sight 0.95 to 1.0, cafe 0.0 | `ingest/tests/test_popularity.py` |
| TC-D14 | DS-6 | Run the pipeline on a country sized area without and with `--bbox` | refused without, accepted with | `ingest/tests/test_pipeline.py` |
| TC-D15 | DS-6 | Overpass answers HTTP 200 with a runtime error remark | treated as a failed attempt and not cached | `ingest/tests/test_overpass.py` |
| TC-D16 | DS-6 | Full run with duplicates, a closed museum, a nameless node and a curation file | 2 places, counts for each drop reason, curated record marked | `ingest/tests/test_pipeline.py` |
| TC-D17 | DS-7 | Spike run where one city fails | report still written, failed city marked FAILED | `ingest/tests/test_spike.py` |
| TC-D18 | DS-7 | Routing comparison on a synthetic table with a 1.25 detour | median ratio 1.25, calibrated error 0 | `ingest/tests/test_routing_spike.py` |
| TC-D19 | DS-8 | Three day forecast with 85 percent rain on day 2 and 2.5 mm on day 3, plus a trip date after the last forecast day | days 2 and 3 rainy, the later date `None`, a second call within 6 h uses the cache and one after 7 h fetches again | `ingest/tests/test_weather.py` |
| TC-D20 | DS-1 | POST `/plan` with no name, an empty name, or `Rome, Georgia` | 422 that lists the cities with data, never a Lisbon plan | `api/tests/test_destinations.py` |
| TC-D21 | DS-2 | Parse `Su off` alone, then `Mo-Su off` | `Su off` is `unknown` and the restaurant is kept; `Mo-Su off` is closed every day and the place is dropped | `ingest/tests/test_hours.py`, `ingest/tests/test_to_place.py` |
| TC-D22 | DS-4 | Dedupe three records with one name in a row 50 m apart | the first two merge, the third (100 m from the seed) stays | `ingest/tests/test_dedupe.py` |
| TC-D23 | DS-4 | Dedupe two fountains that share one wikidata id, 120 m apart, with different names | both kept | `ingest/tests/test_dedupe.py` |
| TC-D24 | DS-4 | Dedupe a ring relation at the city centre plus wall pieces 2 to 6 km apart | one record, placed on the best piece, not at the relation centre | `ingest/tests/test_dedupe.py` |
| TC-D25 | DS-4 | Curate the Ara Pacis museum with the altar 6 m away and a bar with the same name | altar folded into the museum, the bar kept | `ingest/tests/test_curation.py` |
| TC-D26 | DS-6 | Rebuild a city with a matrix setting that fails | error raised, the previous output files are unchanged | `ingest/tests/test_pipeline.py` |
| TC-D27 | DS-6 | Run with a relation whose centre lies outside the bbox | dropped and counted as `dropped_outside_bbox` | `ingest/tests/test_pipeline.py` |

## Metrics for the sprint review

| Metric | Value | Where it comes from |
|--------|-------|---------------------|
| Rome places in the snapshot | 4,549 | `data/cities/rome/report.json` |
| Duplicate records merged | 171, including 91 pieces of the Aurelian Walls into one stop | same report |
| Places dropped inside the Forum and the Vatican walls | 124 | same report, curation zones |
| Copies folded into curated sights | 5 | same report, curation |
| Top sights with hand checked hours and prices | 33 (29 from official sources, 4 applied as inferred) | `data/curation/rome.json` |
| OSM places with real opening hours | 21 to 28% across 4 cities | [`data-spike.md`](data-spike.md) |
| Walking time error vs OSRM, walkable legs | 2.1 min mean, 5.7 min p95 | [`routing-spike.md`](routing-spike.md) |
| Automated tests (Python, whole repo) | 199 passing | `make test-py` |
