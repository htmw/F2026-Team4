# Data slice: user stories, acceptance criteria and test cases

Owner: Sushma (Data). Every story below is covered by automated tests that run in CI on each
pull request (`make test`). The test file is named in the last column.

## User stories

| ID | As a... | I want... | so that... | Acceptance criteria |
|----|---------|-----------|------------|---------------------|
| DS-1 | traveler | the plan to use real places in the city I typed | the trip is for my destination | A Rome request schedules only Rome places. An unknown city gets a 422 that names the cities with data. No silent fallback to Lisbon. |
| DS-2 | traveler | to know which hours and prices are verified | I know what to double check before going | Every place carries `known`, `inferred` or `unknown` on hours and cost. `known` only comes from fully parsed OSM tags or a hand checked official source with a date and URL. |
| DS-3 | optimizer | travel minutes between any two candidates | each day is physically possible | `travel_legs()` returns minutes and mode for every ordered pair. A leg is `walk` only within the traveler's `max_walk_minutes`, otherwise `transit`. No network call. |
| DS-4 | traveler | each sight to appear once | my plan never repeats a place | Records with the same wikidata id within 1 km, or the same name within 60 m, become one. The record with more known facts wins. |
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
| TC-D19 | DS-8 | Forecast with 85 percent rain on day 2 and a date 17 days out | day 2 rainy, far date `None`, second call within 6 h uses the cache | `ingest/tests/test_weather.py` |

## Metrics for the sprint review

| Metric | Value | Where it comes from |
|--------|-------|---------------------|
| Rome places in the snapshot | 4,622 | `data/cities/rome/report.json` |
| Duplicate records merged | 111 | same report |
| Places dropped inside the Forum and the Vatican walls | 125 | same report, curation zones |
| Top sights with hand checked hours and prices | 33 (28 from official sources, 5 applied as inferred) | `data/curation/rome.json` |
| OSM places with real opening hours | 21 to 27% across 4 cities | [`data-spike.md`](data-spike.md) |
| Walking time error vs OSRM, walkable legs | 2.1 min mean, 5.7 min p95 | [`routing-spike.md`](routing-spike.md) |
| Automated tests (whole repo) | 153 passing | `make test` |
