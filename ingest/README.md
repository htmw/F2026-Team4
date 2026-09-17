# /ingest — Discovery + Logistics data (Data team, 2 people)

**You own:** turning a city name into real `Place[]` data the rest of the system can use.

## Contract boundary
- **Output:** objects that validate against [`/contracts/place.schema.json`](../contracts/place.schema.json).
- **Vocabulary:** map source tags (OSM etc.) onto the keys in
  [`/contracts/categories.json`](../contracts/categories.json). Don't invent new categories
  without team agreement.
- Until this is real, everyone develops against [`/fixtures`](../fixtures). Your first job is
  to make `/fixtures` obsolete for at least one city.

## Sprint-1 deliverable
- A script: city name → geocode → fetch tourist POIs → emit valid `Place` objects.
- Parse opening hours where present; set `confidence` **honestly** (`known` only from real
  data, `inferred` for a category default, `unknown` otherwise). Cache raw responses to disk.
- The **data spike** number in [`/docs/data-spike.md`](../docs/data-spike.md): for 3 cities of
  differing data quality, what fraction of POIs have real hours? real prices?
- A **travel matrix** (place-to-place minutes) the Optimizer can consume — start with
  haversine × a factor; compare against real routing in the spike.

## Rules
- Confidence travels with every field. Never label a guess `known`.
- Everyone writes user stories + acceptance criteria + tests for their slice.
