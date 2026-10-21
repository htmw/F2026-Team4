# ingest: the Lisbon data (Data team)

This folder turns OpenStreetMap data for Lisbon into a list of places that the ranker, the
optimizer and the API use. The project covers one city, Lisbon.

## Start here (two minutes)

**Where the data is.** `data/cities/lisbon/places.json`: 6,073 Lisbon places, committed to
the repo. Nothing is downloaded while the app runs.

**How your code gets it.** Never open the JSON files yourself. Ask the catalog:

```python
from ingest.catalog import CityNotAvailable, load_places, travel_legs

places = load_places("Lisbon")        # list of 6,073 dicts, see below
# "Lisboa", "Lisbon, Portugal" and "Lisbon, PT" work too.
# Any other city raises CityNotAvailable (the API answers 422).

candidates = sorted(places, key=lambda p: -p["popularity"])[:100]
legs = travel_legs(candidates, max_walk_minutes=20)
legs[(a_id, b_id)]                    # {"minutes": 12.4, "mode": "walk"}
```

**What one place looks like.** A real record from the file:

```json
{
  "id": "osm:relation/17036063",
  "name": "Museu Calouste Gulbenkian",
  "lat": 38.7378097,
  "lon": -9.1535052,
  "categories": ["museum"],
  "typical_duration_minutes": 90,
  "cost": {"amount": 0.0, "currency": "EUR", "confidence": "unknown"},
  "hours": {
    "mon": [["10:00", "18:00"]], "tue": null, "wed": [["10:00", "18:00"]],
    "thu": [["10:00", "18:00"]], "fri": [["10:00", "18:00"]],
    "sat": [["10:00", "18:00"]], "sun": [["10:00", "18:00"]],
    "confidence": "known"
  },
  "source": "osm",
  "last_verified": "2026-10-17",
  "popularity": 0.59
}
```

- `id`: the OpenStreetMap object. `osm:way/24341353` is way number 24341353 on
  openstreetmap.org. It is stable, so use it as the key. It is not a name: show `name`.
- `hours`: for each day a list of open windows, or `null` for closed that day. Here the
  museum is closed on Tuesdays.
- `cost.amount` is the entry price. The full contract is in
  [`contracts/place.schema.json`](../contracts/place.schema.json).

**Read the confidence before you use a value.** Every `hours` and `cost` carries one:

| Confidence | Meaning | How to use it |
|------------|---------|---------------|
| `known` | Read from real data: a full OSM tag, or a hand checked official source | A hard fact. Do not schedule a visit outside known hours. |
| `inferred` | A default for the category, for example a museum is open 10:00 to 18:00 | A soft guess. Fine for planning, but the app must say it is an estimate. |
| `unknown` | The data exists but we could not read it, or there is no data | Not a value at all. See the two traps below. |

Two traps:

1. `cost` with `"amount": 0.0` and `"confidence": "unknown"` means **price not known**, not
   free. Only `known` (or `inferred` for parks, churches and squares) with amount 0 means free.
2. `hours` with `"confidence": "unknown"` has `null` on every day. Here `null` means **no
   information**, not closed. Check the confidence first.

**Travel times** come from `travel_legs()`, computed on the fly, in minutes:

- walk: straight line distance x 1.3 at 4.5 km/h. Checked against real street routing on
  600 pairs of popular Lisbon places: about 1.8 minutes off per walkable leg (p95 about 5.3).
  See [`docs/routing-spike.md`](../docs/routing-spike.md). It ignores hills, and Lisbon has
  many.
- transit: 10 minutes to reach a stop and wait, then the distance x 1.4 at 15 km/h. A
  planning estimate, not a timetable.
- A leg is `walk` while it fits the traveler's `max_walk_minutes`, otherwise `transit`.

## How the data is built

You only need this to rebuild the data. One command does everything:

```bash
make snapshot-lisbon     # rebuild data/cities/lisbon (downloads once, then reads data/cache)
make data-spike          # hours and price coverage  -> docs/data-spike.md
make routing-spike       # walking time error vs OSRM -> docs/routing-spike.md
```

`ingest/pipeline.py` runs these steps. The code comments use the same numbers.

| Step | File | What it does |
|------|------|--------------|
| 1 | [`geocode.py`](geocode.py) | Finds Lisbon with Nominatim: centre, country and the area to search (the bbox). |
| 2 | [`overpass.py`](overpass.py) | Downloads nine groups of places from the Overpass API: sights, historic, worship, nature, food, nightlife, shopping, public spaces, neighborhoods. Every response is saved in `data/cache/` (not committed), so a rebuild works offline. |
| 3 | [`to_place.py`](to_place.py) | Turns each OSM element into a Place. Uses [`categories.py`](categories.py) for the category, [`hours.py`](hours.py) for `opening_hours` and [`cost.py`](cost.py) for `fee` and `charge`. Drops elements with no name, no position, no category we map, or a centre outside the bbox. |
| 4 | [`popularity.py`](popularity.py) | A 0 to 1 score from how well documented a place is in OSM: translated names, Wikidata and Wikipedia links, heritage status. A proxy, not visitor numbers. |
| 5 | [`dedupe.py`](dedupe.py) | Merges records of the same real place (OSM often maps a sight twice), and turns the 36 pieces of the Aguas Livres aqueduct into one stop. |
| 6 | [`curation.py`](curation.py) | Applies hand checked hours and prices from `data/curation/lisbon.json`. That file does not exist yet (see Known limits). |
| 7 | `pipeline.py` | Writes `places.json`, `destination.json`, `city.json` and `report.json`. |

The other files: [`catalog.py`](catalog.py) is how the app reads the data, [`matrix.py`](matrix.py)
computes travel times, [`weather.py`](weather.py) gives a daily forecast for the trip dates
(Open-Meteo, no key) and `is_outdoor(place)` for the what-if-it-rains flow,
[`cache.py`](cache.py) reads and writes the cache, and [`spike.py`](spike.py) and
[`routing_spike.py`](routing_spike.py) write the two reports in `docs/`.

What is in `data/cities/lisbon/`:

| File | What is in it |
|------|---------------|
| `places.json` | the 6,073 places, one per line, every one valid against the Place contract |
| `destination.json` | name, country and centre of Lisbon, in the Itinerary `destination` shape |
| `city.json` | the names the API accepts (Lisbon, Lisboa...), the bbox, currency, build time, OSM attribution |
| `report.json` | how many records were dropped and why, duplicates merged, hours and price coverage |

A plain `make ingest` writes to `data/out/` instead. That folder is never served, so a test
run cannot change what the app sees. To ship a rebuild, run `make snapshot-lisbon` and
commit `data/cities/lisbon`.

## Words used in the code

| Word | Meaning |
|------|---------|
| OSM | OpenStreetMap, the free map database all our places come from |
| element | one OSM object: a `node` (a point), a `way` (a line or an outline) or a `relation` (a group of other objects) |
| tags | the key=value facts on an OSM element, such as `tourism=museum` or `opening_hours=Tu-Su 10:00-18:00` |
| Overpass | the public API we query to download OSM elements |
| Nominatim | the OSM service that turns a name like Lisbon into a position and an area |
| bbox | bounding box: the search area as south, west, north, east |
| slug | a folder name made from a city name, for example `lisbon` |
| snapshot | the committed output of one full run, in `data/cities/lisbon/` |
| signals | facts kept from the OSM tags while building (names in other languages, wikidata id...) that dedupe and curation need. They are not written to `places.json`. |
| seed | in dedupe, the richest record of a group; only records close to it can join |
| long structure | a wall or aqueduct that OSM splits into many pieces with the same name |
| curation | hand checked facts, from official websites, that overrule the OSM data |
| confidence | `known`, `inferred` or `unknown`, see the table above |

## The confidence rule in detail

Never label a guess `known`.

| Field | `known` | `inferred` | `unknown` |
|-------|---------|------------|-----------|
| `hours` | OSM `opening_hours` fully parsed, or a curated entry from an official source | no hours tag (category default), or a curated entry with only secondary sources | tag present but not in the syntax we read |
| `cost` | parsed `charge`, `fee=no`, or a curated price from an official source | no fee tag on a usually free category (park, church, square...) | `fee=yes` without an amount, a charge with several prices, or no data |

The hours parser is strict on purpose: if any part of the tag is not understood, the whole
value is `unknown` instead of half guessed. `PH` and `SH` (public and school holiday) rules
are skipped because the contract has no holiday field. `typical_duration_minutes` is a
category default unless a curated entry sets it. `rating` is never set because OSM has no
reviews.

## Duplicates in detail

- Walls and aqueducts come as many pieces with one name. Each structure becomes one stop,
  placed on one of its real pieces. A relation that only groups parts is never used for the
  position: its centre is the middle of a bounding box, which can lie far from every part.
- Everything else is grouped around a seed, richest record first: same wikidata id within
  1 km of the seed (100 m when the names differ), or same name within 60 m. Distances are
  measured to the seed, so a row of neighbours cannot chain into one group. A venue (a bar,
  a restaurant, a shop) never merges with a sight. The seed keeps its id and borrows known
  facts from its copies.

## The curation file

A curation file holds the hand checked facts for the top sights. One entry looks like this
(the values are only an illustration):

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
- Matching is by name (any language OSM has) near the given point. Use
  `"match": {"id": "osm:way/123"}` when a name is ambiguous.
- Every entry needs a source URL. Entries that match nothing are listed in `report.json`.
- `confidence` is `high` or `medium` when the facts come from the official site. Use `low`
  when only secondary sources exist or they disagree: the entry is then applied as `inferred`.
- Other records of the same place inside the entry's radius are folded into it, so they
  cannot come back as a free extra stop. A venue is never folded into a sight.
- `exclude_within` drops every place inside a polygon except the ids in `keep`, for a
  ticketed site that OSM maps as many separate sights but people visit with one ticket.

To add the Lisbon file: check the sources, set `checked_on`, save it as
`data/curation/lisbon.json`, add `--curation data/curation/lisbon.json` to the
`snapshot-lisbon` target in the Makefile, then run `make snapshot-lisbon`.

## Known limits

- No hand checked facts for Lisbon yet. The top sights carry raw OSM data only: the
  Jeronimos Monastery, for example, has the museum default hours (`inferred`) and an
  `unknown` price, and the Belem Tower has `unknown` hours because its tag uses seasons.
  Checking the top sights on their official websites is the next data task.
- The Lisbon Oceanarium and the Lisbon Zoo are missing: the sights query does not ask for
  `tourism=aquarium` or `tourism=zoo`. Only the Oceanarium gift shop is in the data.
- Itinerary items carry only `place_id`, so the app shows ids such as `Way/24341353`
  instead of names until the team adds a name to each item or a place lookup.
- About 9% of the hours tags (153 places) stay `unknown`: free text, rules joined by a comma,
  closures on fixed dates, seasons. See [`docs/data-pipeline.md`](../docs/data-pipeline.md).
- Hills: walking times use flat distances, so the climbs to the castle or the viewpoints take
  longer than planned.
- `day_trip` has no OSM mapping; it needs curated entries.

## License

Place data comes from OpenStreetMap, (c) OpenStreetMap contributors, under the ODbL 1.0.
`city.json` carries the attribution, and anything that shows the data should too.
