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

Raw Nominatim and Overpass responses are cached in `data/cache/` (git-ignored). A cached
file is only reused when the city, bbox and query text match exactly.

## Run it

```bash
make ingest CITY="Porto, Portugal"     # any city -> data/out/porto-portugal/
make snapshot-rome                     # rebuild the committed Rome snapshot
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
2. **Fetch** nine Overpass query groups for the bbox: sights, historic, worship, nature, food,
   nightlife, shopping, public spaces, neighborhoods. Squares, fountains and neighborhoods
   only come back when they carry a `wikidata` tag, otherwise every small piazza would.
3. **Convert** each element ([`to_place.py`](to_place.py)): name and coordinates required,
   OSM tags mapped onto the controlled vocabulary ([`categories.py`](categories.py)),
   `opening_hours` parsed ([`hours.py`](hours.py)), fee and charge parsed ([`cost.py`](cost.py)).
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

## Confidence: the one rule

Never label a guess `known`.

| Field | `known` | `inferred` | `unknown` |
|-------|---------|------------|-----------|
| `hours` | OSM `opening_hours` fully parsed, or a curated entry from an official source | no hours tag (category default), or a curated entry with only secondary sources | tag present but outside the supported syntax |
| `cost` | parsed `charge`, `fee=no`, or a curated price from an official source | no fee tag on a usually free category (park, church, square...) | `fee=yes` without an amount, ambiguous charge, or no data |

The hours parser is strict on purpose: if any part of the string is not understood, the whole
value is `unknown` instead of half guessed. `PH` and `SH` (holiday) rules are skipped because
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
- **transit**: 10 minutes to reach and wait for a stop, then the distance x 1.4 at 15 km/h.
  A planning estimate, not a timetable.

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
first request for a city waits. A name OpenStreetMap does not know, or a country or state,
is a 422. OpenStreetMap being unreachable is a 503. Live hours and prices are mostly
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
- Parts of one site that OSM tags with the site's wikidata under another name more than
  100 m away stay separate records. In Rome the one that mattered (Piazza Retta, part of
  St. Peter's Square) is excluded by hand.
- A wall mapped only as one multipolygon keeps the centre of its bounding box, because the
  pipeline fetches centres, not shapes. For a ring of walls that point is off the wall:
  the Porto spike data has one (Muralhas Fernandinas do Porto). No Rome record is affected.

## License

Place data comes from OpenStreetMap, (c) OpenStreetMap contributors, under the ODbL 1.0.
`city.json` carries the attribution and anything that shows the data should too.
