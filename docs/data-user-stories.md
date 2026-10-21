# Data slice: user stories, acceptance criteria and test cases

Owner: Sushma (Data). Every story below is covered by automated tests that run in CI on each
pull request (`make test`). The test file is named in the last column. The project uses one
city, Lisbon.

## User stories

| ID | As a... | I want... | so that... | Acceptance criteria |
|----|---------|-----------|------------|---------------------|
| DS-1 | traveler | the plan to use real places in Lisbon | the trip is built on real data | A Lisbon request schedules only places from the committed Lisbon snapshot. Any other city, a request with no city name, or a namesake in another country (Lisbon, Ohio) gets a 422 that names the city with data. No silent fallback to sample data. |
| DS-2 | traveler | to know which hours and prices are verified | I know what to double check before going | Every place carries `known`, `inferred` or `unknown` on hours and cost. `known` only comes from fully parsed OSM tags or a hand checked official source with a date and URL. |
| DS-3 | optimizer | travel minutes between any two candidates | each day is physically possible | `travel_legs()` returns minutes and mode for every ordered pair. A leg is `walk` only within the traveler's `max_walk_minutes`, otherwise `transit`. No network call. |
| DS-4 | traveler | each sight to appear once | my plan never repeats a place | Around the richest record: same wikidata id within 1 km (100 m when the names differ) or same name within 60 m become one, with no chaining through neighbours. A venue never merges with a sight. Each city wall or aqueduct is one stop placed on one of its pieces. Copies of a curated sight are folded into it. |
| DS-5 | ranker | a popularity value for every place | famous sights rank apart from a corner cafe | Every ingested place has `popularity` in 0..1 built from OSM tag signals, documented as a proxy. |
| DS-6 | data engineer | to rebuild the city data with one command | a data update needs no code change | `make snapshot-lisbon` writes a valid city folder. Raw responses are cached. An area wider than 80 km is refused unless a `--bbox` is given. Overpass errors and timeouts are never cached as data. |
| DS-7 | team | measured numbers for data coverage and travel time error | design decisions rest on data, not guesses | `docs/data-spike.md` reports hours and price coverage for Lisbon. `docs/routing-spike.md` reports haversine error against OSRM foot routing on Lisbon places. |
| DS-8 | traveler | the planner to know about rain and outdoor stops | asking what if it rains can move outdoor stops | Daily forecast for trip dates up to 16 days ahead, `None` further out, cached for 6 hours. `is_outdoor(place)` by primary category. |

## Test cases

| ID | Story | Steps | Expected result | Automated test |
|----|-------|-------|-----------------|----------------|
| TC-D1 | DS-1 | POST `/plan` with destination `{"name": "Lisbon"}` | 200, every scheduled `place_id` is an OSM id from `data/cities/lisbon/places.json`, destination country PT | `api/tests/test_destinations.py` |
| TC-D2 | DS-1 | POST `/plan` with destination `{"name": "New York"}` | 422, message names New York and lists Lisbon | `api/tests/test_destinations.py` |
| TC-D3 | DS-1 | POST `/plan` with `{"city": "Lisbon"}` (no name key) | 200, every place comes from the Lisbon data | `api/tests/test_destinations.py` |
| TC-D4 | DS-2 | Parse weekday hours, an overnight range `22:00-02:00`, then `PH off` | weekday hours `known`, the overnight tail lands on the next day, `PH off` is not `known` (it says nothing about normal days) | `ingest/tests/test_hours.py` |
| TC-D5 | DS-2 | Parse charges `5 EUR`, `2,50 EUR`, `1.500 EUR`, `ENTRY 10`, `adult €10, child €5` | 5, 2.5 and 1500 EUR `known`; ENTRY is not read as Turkish lira; two prices are not `known` | `ingest/tests/test_cost.py` |
| TC-D6 | DS-2 | Apply a curation entry with hours, price and source to a matching place | hours and cost `known`, source `osm+curated`, `last_verified` is the check date | `ingest/tests/test_curation.py` |
| TC-D7 | DS-2 | Load a curation file with unparseable hours or a non ISO currency | load fails with a message naming the entry | `ingest/tests/test_curation.py` |
| TC-D8 | DS-2 | Validate every committed snapshot place against `place.schema.json` | zero errors, no duplicate ids | `ingest/tests/test_catalog.py` |
| TC-D9 | DS-3 | Build legs for three places 1 km apart with `max_walk_minutes=20` | 1 km hop is walk 17.3 min, 2 km hop is transit, 6 legs in total | `ingest/tests/test_matrix.py` |
| TC-D10 | DS-3 | Build legs with `max_walk_minutes=0` | every leg is transit | `ingest/tests/test_matrix.py` |
| TC-D11 | DS-4 | Dedupe a node and a way named the same 30 m apart | one record left, categories merged with the most specific first, known hours kept | `ingest/tests/test_dedupe.py` |
| TC-D12 | DS-4 | Dedupe two bars with the same name 500 m apart | both kept | `ingest/tests/test_dedupe.py` |
| TC-D13 | DS-5 | Score a famous sight and a plain cafe | sight 0.95 to 1.0, cafe 0.0 | `ingest/tests/test_popularity.py` |
| TC-D14 | DS-6 | Run the pipeline on a country sized area without and with `--bbox` | refused without, accepted with | `ingest/tests/test_pipeline.py` |
| TC-D15 | DS-6 | Overpass answers HTTP 200 with a runtime error remark | treated as a failed attempt and not cached | `ingest/tests/test_overpass.py` |
| TC-D16 | DS-6 | Full run with duplicates, a closed museum, a nameless node and a curation file | 2 places, counts for each drop reason, curated record marked | `ingest/tests/test_pipeline.py` |
| TC-D17 | DS-7 | Spike run for Lisbon, then a spike run that fails | the report is written; after a failure the last good report is kept and the exit code is 1 | `ingest/tests/test_spike.py` |
| TC-D18 | DS-7 | Routing comparison on a synthetic table with a 1.25 detour | median ratio 1.25, calibrated error 0 | `ingest/tests/test_routing_spike.py` |
| TC-D19 | DS-8 | Three day forecast with 85 percent rain on day 2 and 2.5 mm on day 3, plus a trip date after the last forecast day | days 2 and 3 rainy, the later date `None`, a second call within 6 h uses the cache and one after 7 h fetches again | `ingest/tests/test_weather.py` |
| TC-D20 | DS-1 | POST `/plan` with no name, an empty name, or `Lisbon, Ohio` | 422 that lists the city with data, never a plan from sample data | `api/tests/test_destinations.py` |
| TC-D21 | DS-2 | Parse `Su off` alone, then `Mo-Su off` | `Su off` is `unknown` and the restaurant is kept; `Mo-Su off` is closed every day and the place is dropped | `ingest/tests/test_hours.py`, `ingest/tests/test_to_place.py` |
| TC-D22 | DS-4 | Dedupe three records with one name in a row 50 m apart | the first two merge, the third (100 m from the seed) stays | `ingest/tests/test_dedupe.py` |
| TC-D23 | DS-4 | Dedupe two fountains that share one wikidata id, 120 m apart, with different names | both kept | `ingest/tests/test_dedupe.py` |
| TC-D24 | DS-4 | Dedupe a ring relation at the city centre plus wall pieces 2 to 6 km apart | one record, placed on the best piece, not at the relation centre | `ingest/tests/test_dedupe.py` |
| TC-D25 | DS-4 | Curate a monastery whose church record sits 6 m away, next to a bar that carries one of its names | the church folded into the monastery, the bar kept | `ingest/tests/test_curation.py` |
| TC-D26 | DS-6 | Rebuild with a curation file in which two entries match the same place | error raised, the previous output files are unchanged | `ingest/tests/test_pipeline.py` |
| TC-D27 | DS-6 | Run with a relation whose centre lies outside the bbox | dropped and counted as `dropped_outside_bbox` | `ingest/tests/test_pipeline.py` |
| TC-D28 | DS-4 | Dedupe a landmark record (open all day, free) with a museum record of the same monastery | one museum: museum default hours, price `unknown` instead of assumed free | `ingest/tests/test_dedupe.py` |
| TC-D29 | DS-1 | Ask the catalog for Lisbon, Lisboa, Lisbon, PT and Lisbon, Portugal, then for Lisbon, Ohio and Porto | the Lisbon data for the first four, `CityNotAvailable` naming Lisbon for the others | `ingest/tests/test_catalog.py` |

## Metrics for the sprint review

| Metric | Value | Where it comes from |
|--------|-------|---------------------|
| Lisbon places in the snapshot | 6,073 | `data/cities/lisbon/report.json` |
| Duplicate records merged | 127, including 36 pieces of the Aguas Livres aqueduct into one stop | same report |
| Places dropped outside the city boundary | 8 | same report |
| Top sights with hand checked hours and prices | none yet, the next data task | `data/curation/lisbon.json` (not written yet) |
| OSM places with real opening hours | 25% (29% of the 100 most popular sights) | [`data-spike.md`](data-spike.md) |
| Walking time error vs OSRM, walkable legs | 1.8 min mean, 5.3 min p95 | [`routing-spike.md`](routing-spike.md) |
| Automated tests (Python, whole repo) | 191 passing, 173 of them for the data slice | `make test-py` |
