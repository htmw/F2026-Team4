# /ingest: city data (Data team)

Turns a city name into `Place` records the ranker and the optimizer can trust, plus the
travel times between them. Everything here speaks the shapes in [`/contracts`](../contracts).

The project uses one city, Lisbon. Its snapshot is committed in `data/cities/lisbon`.

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
make snapshot-lisbon                   # rebuild the committed Lisbon snapshot
make data-spike                        # hours and price coverage -> docs/data-spike.md
make routing-spike                     # haversine vs OSRM walking -> docs/routing-spike.md
make ingest                            # a scratch run -> data/out/lisbon-portugal/
```

Direct use, with every option:

```bash
uv run python -m ingest "Lisbon, Portugal" --slug lisbon --alias Lisboa --out data/cities --matrix-top 0
uv run python -m ingest --help
```

A geocoded area wider or taller than 80 km is refused (that is a region, not a city).
Passing `--bbox` skips that check, because then the geocoded box is only used for the
name, country and centre. Lisbon needs no bbox: its city boundary is about 12 by 12 km.

## How a record is built

1. **Geocode** the name with Nominatim: centre, country, default bbox.
2. **Fetch** nine Overpass query groups for the bbox: sights, historic, worship, nature, food,
   nightlife, shopping, public spaces, neighborhoods. Squares, fountains and neighborhoods
   only come back when they carry a `wikidata` tag, otherwise every small square would.
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
   - City walls and aqueducts come as dozens of pieces with one name (Lisbon has 36 pieces
     of the Aguas Livres aqueduct). Each structure becomes one stop, placed on its best node
     or way. A relation that groups parts (site, route, building, waterway) is never used for
     the position: its centre is the middle of a bounding box, which for a long or ring
     shaped structure can lie far from every part. A single area relation (a multipolygon)
     is used only when the structure has no node or way at all.
   - Everything else is grouped around a seed, richest record first: same wikidata id within
     1 km of the seed (100 m when the names differ), or same name within 60 m. Distances are
     measured to the seed, so a row of neighbours cannot chain into one group. A venue never
     merges with a sight. The seed keeps its id and borrows known facts from its copies.
6. **Curation** ([`curation.py`](curation.py)): hand checked hours, prices and visit lengths
   for the sights that matter most, from `data/curation/<city>.json`. Lisbon has no
   curation file yet (see Known limits).

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

A curation file holds the hand checked facts for the top sights of the city. Each entry
looks like this (the values are only an illustration):

```json
{
  "name": "Example Museum",
  "match": {"names": ["Museu Exemplo"], "near": [38.7100, -9.1400], "radius_m": 150},
  "opening_hours": "Tu-Su 10:00-18:00",
  "price": {"amount": 10.0, "currency": "EUR"},
  "duration_minutes": 90,
  "confidence": "high",
  "sources": ["https://..."],
  "notes": "Last entry 30 minutes before closing."
}
```

- `opening_hours` uses the OSM syntax and goes through the same strict parser. A typo stops
  the run instead of becoming a known fact.
- Matching is by name (any language variant OSM has) near the given point. Use
  `"match": {"id": "osm:way/123"}` when a name is ambiguous.
- Every entry needs a source URL. Entries that match nothing are listed in `report.json`.
- `confidence` is `high` or `medium` when the facts come from the official site. Use `low` when
  only secondary sources exist or they disagree: the entry is then applied as `inferred`.
- Hours are the doors-open times. Last entry, free days and special closures go in `notes`.
- Other records of the same place are folded in: anything within the entry's radius that
  carries one of its names (a monument mapped once as a building and once as a point). A
  venue is never folded into a sight or a sight into a venue, so a bar named after a
  monument stays a bar, and a neighbourhood is never folded. Two entries that match the same
  place stop the run.
- Folding uses the same radius as matching, so keep the radius tight around the site: a wide
  radius can swallow a free viewpoint or square next to a paid sight.
- `exclude_within` drops every place inside a polygon except the ids in `keep`. Use it for a
  ticketed site that OSM maps as many separate sights but people visit with one ticket. A
  zone never drops a neighbourhood, because the label point of a whole district can fall
  inside.

To add the Lisbon file: check the sources, set `checked_on`, save it as
`data/curation/lisbon.json`, add `--curation data/curation/lisbon.json` to the
`snapshot-lisbon` target, then run `make snapshot-lisbon`.

## Travel times

[`matrix.py`](matrix.py):

- **walk**: straight line distance x 1.3 / 4.5 km/h. Against OSRM foot routing on 600 pairs of
  popular Lisbon places this is off by about 1.8 minutes per walkable leg (p95 about 5.3),
  slightly on the long side. See [`docs/routing-spike.md`](../docs/routing-spike.md). Neither
  method knows about hills, and Lisbon has many.
- **transit**: 10 minutes to reach and wait for a stop, then the distance x 1.4 at 15 km/h.
  A planning estimate, not a timetable.

A leg is `walk` while it fits the traveler's `max_walk_minutes`, otherwise `transit`.

## Using the data from other folders

```python
from ingest.catalog import CityNotAvailable, load_city, travel_legs

city = load_city("Lisbon")                # also "Lisboa", "Lisbon, Portugal"; raises CityNotAvailable
candidates = sorted(city.places, key=lambda p: -p["popularity"])[:150]  # or the ranker top N
legs = travel_legs(candidates, max_walk_minutes=profile["max_walk_minutes"])
legs[(a_id, b_id)]                        # {"minutes": 12.4, "mode": "walk"}
```

`legs` is the shape `optimizer/travel.py` reads (that file is on the optimizer branch,
PR 13, until it merges). Lookup order for a name: committed snapshots in `data/cities`,
then `/fixtures`, then any folder in `WANDERWISE_EXTRA_CITIES`. `api/contracts.load_places()`
goes through the same catalog, so Lisbon comes from the snapshot. The small hand made
sample in `/fixtures` has the same name, so the snapshot hides it.

A name matches the city name or an alias. "City, Region" also matches when the last part is
the city's country, so "Lisbon, PT" works but "Lisbon, Ohio" does not. Any other city, and a
request without a city name, gets the same clear error.

A plain `make ingest` writes to `data/out` and is not served, so a test run on one laptop
never changes what the API or the ranker sees. To try a local run in the app, point
`WANDERWISE_EXTRA_CITIES=data/out` at it. It can add data but never replace the committed
Lisbon snapshot. To ship a rebuild, run `make snapshot-lisbon` and commit `data/cities/lisbon`.
Output files are written with Unix line ends on every OS, so a rebuild on Windows gives the
same bytes.

For the what-if-it-rains flow, [`weather.py`](weather.py) gives a daily forecast for the trip
dates (Open-Meteo, no key needed, cached for 6 hours) and `is_outdoor(place)`.

## Known limits

- No hand checked facts for Lisbon yet. The top sights carry raw OSM data only: the
  Jeronimos Monastery, for example, gets default hours and an assumed free entry. Checking
  the top sights on their official sites is the next data task. See
  [`docs/data-spike.md`](../docs/data-spike.md) for how thin raw coverage is.
- Hills: walking times use flat distances, so climbs to the castle or the viewpoints take
  longer than planned.
- Seasonal hours: the contract holds one weekly pattern, so curated hours will need the
  timetable that covers the demo dates.
- `day_trip` has no OSM mapping yet; it needs curated entries.
- Parts of one site that OSM tags with the site's wikidata under another name more than
  100 m away stay separate records.
- A wall mapped only as one multipolygon keeps the centre of its bounding box, because the
  pipeline fetches centres, not shapes. For a ring of walls that point is off the wall.

## License

Place data comes from OpenStreetMap, (c) OpenStreetMap contributors, under the ODbL 1.0.
`city.json` carries the attribution and anything that shows the data should too.
