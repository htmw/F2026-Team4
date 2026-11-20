# /ingest: city data (Data team)

Turns a city name into `Place` records the ranker and the optimizer can trust, plus the
travel times between them. Everything here speaks the shapes in [`/contracts`](../contracts).

## What you get per city

Each run writes one folder (`data/out/<city>/` by default, `data/cities/<city>/` for a
committed snapshot):

| File | What is in it |
|------|---------------|
| `places.json` | `Place[]`, every record valid against [`place.schema.json`](../contracts/place.schema.json) |
| `destination.json` | name, country, lat, lon in the Itinerary `destination` shape |
| `city.json` | aliases the API accepts, bbox, currency, build time, OSM attribution |
| `report.json` | counts, drop reasons, duplicates merged, hours and price coverage, curation result |
| `matrix.json` | walk and transit minutes for the most popular places (skipped with `--matrix-top 0`) |
| `stop_walks.json` | minutes from each place to its nearest bus stop or station (when OSM has stops) |
| `descriptions.json` | a "what is this place" line per place: `{"text", "source", "website"?}`, source `wikipedia` or `openstreetmap`; `website` is the place's own site when OSM has one |

The two last files sit beside `places.json`, not inside it, so every place still matches the
Place contract unchanged.

Raw Nominatim and Overpass responses are cached in `data/cache/` (git-ignored). A cached
file is only reused when the city, bbox and query text match exactly.

## Run it

```bash
make ingest CITY="Porto, Portugal"     # any city -> data/out/porto-portugal/
make snapshot-rome                     # rebuild the committed Rome snapshot
make data-quality                      # what a traveler gets in 8 cities -> docs/data-quality.md
make data-spike                        # hours and price coverage -> docs/data-spike.md
make routing-spike                     # haversine vs OSRM walking -> docs/routing-spike.md
```

Direct use, with every option:

```bash
uv run python -m ingest "London, UK" --bbox 51.45,-0.25,51.56,0.02 --slug london --alias "Greater London"
uv run python -m ingest --help
```

A geocoded area wider or taller than 80 km is refused (that is a region, not a city).
Passing `--bbox` skips that check, because then the geocoded box is only used for the
name, country and centre.

## How a record is built

1. **Geocode** the name with Nominatim: centre, country, default bbox.
2. **Fetch** nine Overpass query groups for the bbox: sights, historic, worship (every church,
   and temples, mosques and other places of worship that have Wikidata), nature, food,
   nightlife, shopping, public spaces, neighborhoods. Squares, fountains and neighborhoods
   only come back when they carry a `wikidata` tag, otherwise every small piazza would.
3. **Convert** each element ([`to_place.py`](to_place.py)): name and coordinates required,
   OSM tags mapped onto the controlled vocabulary ([`categories.py`](categories.py)),
   `opening_hours` parsed ([`hours.py`](hours.py)), fee and charge parsed ([`cost.py`](cost.py)).
   Names stay as mapped when they are in Latin letters ("Grand Palais", not the "Great
   Palace" of its `name:en`); another script gets `name:en`, else `int_name` (Sion Fort for
   सायन किल्ला). A place with no Latin-script name at all (only an Urdu, Thai or Korean name) is
   dropped. Duplicates still match on the mapped name.
   An outlet of a global chain (Domino's, Starbucks, KFC... by `brand` or name) is dropped;
   local chains such as Pista House stay, but only their most popular outlet per city (central
   Tokyo has dozens of Tully's Coffee; a plan should not visit three).
   A market, landmark or viewpoint is dropped unless it has Wikidata, Wikipedia or heritage
   tags: OSM maps every vegetable and footwear market and every plaque, and only the famous
   ones are sights (Crawford Market stays, "Sabji Market" goes). Typed sights such as museums,
   restaurants and cafes, and the pieces of a city wall or aqueduct, are kept.
   A school, college or university is dropped unless it has Wikidata, Wikipedia or heritage
   tags: mappers sometimes tag one as a sight (a college in Karimnagar is a "viewpoint").
   A place whose hours name every day as closed is dropped. A place that only lists its
   closed days ("Su off") keeps `unknown` hours: the open days are not stated. A place whose
   centre falls outside the bbox is dropped too: Overpass returns anything that touches the
   box, and a long relation can have its centre kilometres away.
4. **Popularity** ([`popularity.py`](popularity.py)): a 0..1 proxy from translated names,
   Wikidata and Wikipedia links, heritage status and how well documented the place is.
5. **Duplicates** ([`dedupe.py`](dedupe.py)):
   - City walls and aqueducts come as dozens of pieces with one name (Rome has 91 pieces of
     the Aurelian Walls). Each structure becomes one stop, placed on its best node or way.
     A relation that groups parts (site, route, building, waterway) is never used for the
     position: its centre is the middle of a bounding box, which for the ring of the
     Aurelian Walls is next to the Colosseum. A single area relation (a multipolygon) is
     used only when the structure has no node or way at all.
   - Everything else is grouped around a seed, richest record first: same wikidata id within
     1 km of the seed (100 m when the names differ), or same name within 60 m. Distances are
     measured to the seed, so a row of neighbours cannot chain into one group. A venue never
     merges with a sight. The seed keeps its id and borrows known facts from its copies.
6. **Curation** ([`curation.py`](curation.py)): hand checked hours, prices and visit lengths
   for the sights that matter most, from `data/curation/<city>.json`.

## Where each piece of data comes from

| What the traveler sees | Source | Marked as |
|------------------------|--------|-----------|
| Place names, location, kind of place | OpenStreetMap (Overpass), fetched live per city | — |
| Price "€18.00" or "Free" | OSM `charge` / `fee=no`, or a hand checked official source (Rome curation) | verified (`known`) |
| Price "≈ €25.00" | `TYPICAL_PRICE` in `cost.py`: a rough October 2026 price per kind of place for 21 currencies; every other currency converts `BASE_USD` at a rough rate (`USD_RATE`). Paid towers and observation decks: twice a museum ticket. | estimated (`inferred`) |
| Free parks, churches, squares | `FREE_BY_DEFAULT` in `categories.py` | estimated (`inferred`) |
| "Hours verified" + "Open 9:00 AM – 6:00 PM" | OSM `opening_hours`, fully parsed, or Rome curation | `known` |
| "Hours estimated" + "Open …" | `DEFAULT_HOURS` in `categories.py`: the usual hours for that kind of place, used when OSM has no hours or hours we cannot read | `inferred` |
| What the place is, "(Wikipedia)" | First two sentences of the English Wikipedia article, found through the OSM `wikidata` or `wikipedia` tag (Wikidata API, then Wikipedia API). Text is CC BY-SA and credited on screen. | `description_source: wikipedia` |
| What the place is, plain line | Built from OSM tags: kind, cuisine, religion, year built, or the OSM `description` | `description_source: openstreetmap` |
| "Website" link | OSM `website` or `contact:website`, only `http`/`https` links kept | — |
| Weather pill under each day, rain warning | Open-Meteo daily forecast for the trip dates (up to 16 days ahead), cached 6 hours; "Forecast unavailable" when there is none | forecast |
| "X min walk" between stops | Straight line x 1.3 at 4.5 km/h (checked against OSRM, see Travel times) | estimate |
| "X min transit (incl. Y min walk to and from the stop)" | Walk to the nearest OSM bus stop or station from each place, a 4 minute wait, the ride at 15 km/h | estimate |

Nothing here is ever labelled `known` unless it came from OSM or an official source. Every
estimate says so on screen (≈, "estimated", "Some travel times are estimates").

## Confidence: the one rule

Never label a guess `known`.

| Field | `known` | `inferred` | `unknown` |
|-------|---------|------------|-----------|
| `hours` | OSM `opening_hours` fully parsed, or a curated entry from an official source | no hours tag, or a tag we cannot read: the category's usual hours; or a curated entry with only secondary sources | not produced any more (older saved cities are filled in when they load) |
| `cost` | parsed `charge`, `fee=no`, or a curated price from an official source | a usually free category (park, church, square...); otherwise a typical price per person in that currency (`TYPICAL_PRICE`, or `BASE_USD` x `USD_RATE`); `fee=yes` without an amount or an ambiguous charge also gets the typical price | only a place with no currency at all (`XXX`) |

The hours parser is strict on purpose: if any part of the string is not understood, the parser
gives up instead of half guessing, and the place gets its category's usual hours marked
`inferred`, never a half parsed `known`. `PH` and `SH` (holiday) rules are skipped because
the contract has no holiday field. `typical_duration_minutes` is a category default unless a
curated entry sets it. `popularity` is a proxy, documented as one, and `rating` is never set
because OSM has no reviews.

## Curation

`data/curation/rome.json` holds the hand checked facts for the Rome demo. Each entry:

```json
{
  "name": "Pantheon",
  "match": {"names": ["Pantheon"], "near": [41.8986, 12.4769], "radius_m": 250},
  "opening_hours": "Mo-Su 09:00-19:00",
  "price": {"amount": 7.0, "currency": "EUR"},
  "duration_minutes": 30,
  "confidence": "high",
  "sources": ["https://cultura.gov.it/luogo/pantheon"],
  "notes": "Last entry 18:30."
}
```

- `opening_hours` uses the OSM syntax and goes through the same strict parser. A typo stops
  the run instead of becoming a known fact.
- Matching is by name (any language variant OSM has) near the given point. Use
  `"match": {"id": "osm:way/123"}` when a name is ambiguous.
- Every entry needs a source URL. Entries that match nothing are listed in `report.json`.
- `confidence` is `high` or `medium` when the facts come from the official site. Use `low` when
  only secondary sources exist or they disagree: the entry is then applied as `inferred`.
- Hours are the doors-open times. Last entry, free Sundays and special closures go in `notes`.
- Other records of the same place are folded in: anything within the entry's radius that
  carries one of its names (the Ara Pacis altar next to the Ara Pacis museum). A venue is
  never folded into a sight or a sight into a venue, so the San Clemente bar stays a bar,
  and a neighbourhood is never folded. Two entries that match the same place stop the run.
- Folding uses the same radius as matching, so keep the radius tight around the site. The
  Colosseum uses 150 m: at 300 m it would swallow the free Colosseo viewpoint on the street
  above it.
- `exclude_within` drops every place inside a polygon except the ids in `keep`. Rome uses it
  for the Roman Forum and Palatine, and for the inside of the Vatican walls: OSM maps every
  temple and gallery there as its own sight, but they are visited with one ticket. A zone
  never drops a neighbourhood, because the label point of a whole district can fall inside.

To refresh a city, check the sources again, update `checked_on`, then `make snapshot-rome`.

## Travel times

[`matrix.py`](matrix.py):

- **walk**: straight line distance x 1.3 / 4.5 km/h. Against OSRM foot routing on 600 pairs of
  popular Rome places this is off by about 2 minutes per walkable leg (p95 under 6), slightly
  on the long side. See [`docs/routing-spike.md`](../docs/routing-spike.md).
- **transit**: the walk from the place to its nearest bus stop or station, a 4 minute wait,
  the distance x 1.4 at 15 km/h, and the walk from the stop nearest the next place. The walks
  come from `stop_walks.json` (straight line to the nearest OSM stop x 1.3 at 4.5 km/h, at most
  15 min); without it, 3 minutes each way. The leg carries `walk_minutes` so the day's walking
  total includes it. A planning estimate, not a timetable.

A leg is `walk` while it fits the traveler's `max_walk_minutes`, otherwise `transit`.

## Using the data from other folders

```python
from ingest.catalog import CityNotAvailable, load_city, travel_legs

city = load_city("Rome")                  # also "Roma", "Rome, Italy"; raises CityNotAvailable
candidates = sorted(city.places, key=lambda p: -p["popularity"])[:150]  # or the ranker top N
legs = travel_legs(candidates, max_walk_minutes=profile["max_walk_minutes"])
legs[(a_id, b_id)]                        # {"minutes": 12.4, "mode": "walk"}
```

`legs` is the shape `optimizer/travel.py` reads (that file is on the optimizer branch,
PR 13, until it merges). Lookup order for a name: committed snapshots in `data/cities`,
then `/fixtures`, then any folder in `WANDERWISE_EXTRA_CITIES`. `api/contracts.load_places()`
goes through the same catalog, so Lisbon comes from the fixtures and Rome from the snapshot.

**Any other city is fetched live** by `fetch_live()`: Nominatim finds the city, Overpass
returns everything within 5 km of its centre in one query, and the same pipeline turns it
into places (no curation). The result is kept in `data/live/<city>-<country>/`, so only the
first request for a city waits. After 30 days it is fetched again, and the old copy is used
if OpenStreetMap is down at that moment. A name OpenStreetMap does not know, or a country or state
over 100 km across, is a 422 (Delhi and Mexico City, states in OSM, still plan). OpenStreetMap being unreachable is a 503. Live hours and prices are mostly
`inferred`, and each stop is labelled so. `WANDERWISE_LIVE_INGEST=0` turns it off.

A name matches the city name or an alias. "City, Region" also matches when the last part is
the city's country, so "Rome, IT" and "Rome, Lazio, Italy" work but "Rome, Georgia" does
not. A request without a city name gets the same clear error as an unknown city.

A plain `make ingest` writes to `data/out` and is not served, so a test run on one laptop
never changes what the API or the ranker sees. To try a local city in the app, point
`WANDERWISE_EXTRA_CITIES=data/out` at it. It can add cities but never replace Rome or
Lisbon. To ship a city, build it into `data/cities` (as `make snapshot-rome` does) and
commit it. Output files are written with Unix line ends on every OS, so a rebuild on
Windows gives the same bytes.

For the what-if-it-rains flow, [`weather.py`](weather.py) gives a daily forecast for the trip
dates (Open-Meteo, no key needed, cached for 6 hours) and `is_outdoor(place)`.

## Known limits

- One curated city (Rome). Every other city is fetched live and carries raw OSM coverage
  only. See [`docs/data-spike.md`](../docs/data-spike.md) for how thin that is. Small cities
  can be very thin: Karimnagar has 23 places.
- The first request for a live city waits for the fetch. Only the main Overpass server is
  used (no public mirror worked in tests), so when it is down, new cities get a 503 after
  three tries. Cities fetched before still load.
- Seasonal hours: the contract holds one weekly pattern, so the curated hours are the winter
  timetable that covers the demo dates. Change them when the season changes.
- `day_trip` has no OSM mapping yet; it needs curated entries.
- Typical prices and exchange rates are rough October 2026 figures, shown with ≈. They are
  worth a check against a cost-of-living source (for example Numbeo) and a refresh each year.
- Estimated hours ignore closing days: a restaurant whose unreadable tag says "closed
  Sunday" gets its usual hours every day.
- The walk to transit uses the nearest stop in a straight line, which is not always on the
  right route.
- Descriptions are English Wikipedia only; a famous place with no English article gets the
  plain OSM line. Saved cities from before descriptions existed have none until they are
  fetched again (`rm -rf data/live/*`). Rome, the committed snapshot, is rebuilt with
  `make snapshot-rome`, which passes `--wikipedia` (the command line only asks Wikipedia when
  told to).
- Parts of one site that OSM tags with the site's wikidata under another name more than
  100 m away stay separate records. In Rome the one that mattered (Piazza Retta, part of
  St. Peter's Square) is excluded by hand.
- A wall mapped only as one multipolygon keeps the centre of its bounding box, because the
  pipeline fetches centres, not shapes. For a ring of walls that point is off the wall:
  the Porto spike data has one (Muralhas Fernandinas do Porto). No Rome record is affected.

## License

Place data comes from OpenStreetMap, (c) OpenStreetMap contributors, under the ODbL 1.0.
`city.json` carries the attribution and anything that shows the data should too.
Descriptions marked `wikipedia` are from Wikipedia, under CC BY-SA 4.0; the website credits
"(Wikipedia)" next to each one.
