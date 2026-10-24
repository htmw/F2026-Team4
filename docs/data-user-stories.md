# Data slice: user stories, acceptance criteria and test cases

Owner: Sushma (Data). Every story below is covered by automated tests that run in CI on each
pull request (`make test`). The test file is named in the last column.

## User stories

| ID | As a... | I want... | so that... | Acceptance criteria |
|----|---------|-----------|------------|---------------------|
| DS-1 | traveler | the plan to use real places in the city I typed | the trip is for my destination | A Rome request schedules only Rome places. A request with no city name gets a 422. Any other city is fetched live (DS-9). No silent fallback to Lisbon. |
| DS-2 | traveler | to know which hours and prices are verified | I know what to double check before going | Every place carries `known`, `inferred` or `unknown` on hours and cost. `known` only comes from fully parsed OSM tags or a hand checked official source with a date and URL. |
| DS-3 | optimizer | travel minutes between any two candidates | each day is physically possible | `travel_legs()` returns minutes and mode for every ordered pair. A leg is `walk` only within the traveler's `max_walk_minutes`, otherwise `transit`. No network call. |
| DS-4 | traveler | each sight to appear once | my plan never repeats a place | Around the richest record: same wikidata id within 1 km (100 m when the names differ) or same name within 60 m become one, with no chaining through neighbours. A venue never merges with a sight. Each city wall or aqueduct is one stop placed on one of its pieces. Copies of a curated sight are folded into it. |
| DS-5 | ranker | a popularity value for every place | famous sights rank apart from a corner cafe | Every ingested place has `popularity` in 0..1 built from OSM tag signals, documented as a proxy. |
| DS-6 | data engineer | to ingest any city by name | we can add a city without code changes | `make ingest CITY=...` writes a valid city folder. Raw responses are cached. Large cities work with `--bbox`. Overpass errors and timeouts are never cached as data. |
| DS-7 | team | measured numbers for data coverage and travel time error | design decisions rest on data, not guesses | `docs/data-spike.md` reports hours and price coverage for 4 cities. `docs/routing-spike.md` reports haversine error against OSRM foot routing. |
| DS-9 | traveler | a plan for any city I type, not only Rome and Lisbon | I can use the app wherever I travel | A city with no committed data is fetched live from OpenStreetMap (Nominatim, then one Overpass query for 5 km around the centre) and saved in `data/live/`, so only the first request waits. A saved city older than 30 days is fetched again; if OpenStreetMap is down then, the old copy is used. Only cities, towns and villages match, never a shop with the same name. A country or state, or a name OpenStreetMap does not know, gets a 422. OpenStreetMap unreachable gets a 503 after three tries of the main server (5 s and 15 s apart, 120 s each at most). A city too dense for one query is fetched again for 2.5 km. The itinerary shows the city with its country, real place names and prices in the local currency. |
| DS-8 | traveler | the planner to know about rain and outdoor stops | asking what if it rains can move outdoor stops | Daily forecast for trip dates up to 16 days ahead, `None` further out, cached for 6 hours. `is_outdoor(place)` by primary category. |

## Test cases

| ID | Story | Steps | Expected result | Automated test |
|----|-------|-------|-----------------|----------------|
| TC-D1 | DS-1 | POST `/plan` with destination `{"name": "Rome"}` | 200, every scheduled `place_id` is in `data/cities/rome/places.json`, destination country IT | `api/tests/test_destinations.py` |
| TC-D2 | DS-1 | With live ingest off, POST `/plan` with destination `{"name": "New York"}` | 422, message names New York and lists Rome and Lisbon | `api/tests/test_destinations.py` |
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
| TC-D28 | DS-9 | Ask for Porto twice with OpenStreetMap faked | fetched once with one Overpass query, saved, second request reads the folder | `ingest/tests/test_live.py` |
| TC-D29 | DS-9 | POST `/plan` for a live city | 200, items carry the place name | `ingest/tests/test_live.py` |
| TC-D30 | DS-9 | Plan "karimnagar" | title "Karimnagar, India", totals in INR | `ingest/tests/test_live.py` |
| TC-D31 | DS-9 | Ask for "Portugal", then for a name OpenStreetMap does not know | "a country, not a city"; 422 | `ingest/tests/test_live.py` |
| TC-D32 | DS-9 | OpenStreetMap down, then the main server hanging, then busy once | 503, 503 after three tries at 120 s each, then 200 from the second try | `ingest/tests/test_live.py` |
| TC-D33 | DS-9 | Ask for Rome and Lisbon with live ingest on | served from the snapshot and fixtures, nothing fetched | `ingest/tests/test_live.py` |
| TC-D34 | DS-9 | Look up the currency of every ISO country | none falls back to `XXX`; Colombia COP, Japan JPY | `ingest/tests/test_cost.py` |
| TC-D35 | DS-2 | Parse `Fr-Sa 19:00-26:00` and `Mo-Fr 09:00-12:00, We 14:00-18:00, Sa 10:00-14:00` | both `known`; the 26:00 tail lands on the next day; the comma rule adds Wednesday afternoon | `ingest/tests/test_hours.py` |
| TC-D37 | DS-9 | Overpass answers 504 for the 5 km query | the same query is not repeated; it is sent once more for half the distance and the plan is made | `ingest/tests/test_live.py` |
| TC-D38 | DS-9 | Ask for a saved city that is 31 days old, once with OpenStreetMap up and once with it down | fetched again (not from the raw cache); with OpenStreetMap down the old copy is served | `ingest/tests/test_live.py` |
| TC-D39 | DS-9 | Convert a college tagged `tourism=viewpoint`, then a university with a Wikidata id | the college is dropped as `school`; the famous university stays | `ingest/tests/test_to_place.py` |
| TC-D36 | DS-2 | Parse `Apr-Oct Mo-Su 09:00-18:00` | stays `unknown`: one weekly pattern cannot say which season | `ingest/tests/test_hours.py` |

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
| Live cities tried on a laptop | Porto 3,252 places (63 duplicates merged), Karimnagar 23, Hyderabad and New York planned with real place names | backend log, October 2026 |
| Automated tests (Python, whole repo) | 212 passing | `make test-py` |
