# Ranking dataset preparation

Prepare training, validation and test examples from real OpenStreetMap places.
This is a standalone data tool: it does not modify the application or train a model.

## Data and labels

- Places come from the existing ingest catalog. Existing cost/hour confidence,
  popularity and any supplied ratings are retained.
- Traveler profiles and relevance grades (0–4) are simulated using the existing
  `ranker.synthetic` helpers. These are not real traveler judgments.
- Missing ratings are not invented. The existing feature code encodes them as 0;
  that is not a real zero-star review.
- Budgets are explicit simulation choices in local currency, not exchange rates.
- Features are calculated by the current `ranker.features.extract_features`,
  including `price_ratio`. No feature or model code is changed by this contribution.

## Small offline example

From the repository root:

```bash
uv sync
uv run python -m ranker.prepare_manifest --manifest ranker/examples/manifest.json --snapshots ranker/examples/snapshots --offline --output data/ranking_sample
```

The committed example contains 15 real place records from Paris and 15 from Tokyo,
selected from the earlier PR #26 source snapshots. Paris is for training/validation;
Tokyo is test-only. It generates 50 simulated traveler examples per city with 15
candidates each. It is a smoke-test example, not a dataset for reporting model quality.
These are historical samples, not a newly fetched or curated dataset.
The example's source ID lists describe only these 15-record inputs per city.
The snapshot locks retain the original collection metadata and hashes for these inputs.

Repeat with a different output folder to verify reproducibility:

```bash
uv run python -m ranker.prepare_manifest --manifest ranker/examples/manifest.json --snapshots ranker/examples/snapshots --offline --output data/ranking_sample_rebuilt
```

Exact rebuilding requires the same inputs, code and dependencies. The command fixes
`PYTHONHASHSEED=0` so the existing helpers have stable set iteration. Existing output
folders are not overwritten. Offline mode fails if a snapshot is missing or changed.

## Full preparation

```bash
uv run python -m ranker.prepare_manifest
```

`ranker/dataset_manifest.json` configures 12 training/development cities and three
test-only cities (Tokyo, Bogota and Hyderabad), 500 simulated travelers per city,
15 candidates per traveler and at most 500 sampled places per city.
The command reuses saved ranking snapshots, otherwise calls the existing
`ingest.catalog.fetch_live`. That catalog may reuse its saved city cache; a new
ranking snapshots folder does not force a new network download.

Default local outputs:

- `data/ranking_dataset_v3/`: train, validation, test, manifest and summary JSON.
- `data/ranking_sources_v3/`: compact source snapshots, metadata, all source IDs and hashes.

Both folders are ignored by Git and are deliberately excluded from this PR.
Keep large generated datasets outside Git and share them separately with the model team.
The historical run had 4,786 train, 1,214 validation and 1,500 test queries. Rebuilding
against current source data/code is a new run: read its summary rather than assuming
those historical counts or results still apply.

To rebuild a locally saved full collection without fetching:

```bash
uv run python -m ranker.prepare_manifest --offline --output data/ranking_dataset_rebuilt
```

## Load examples for model functions

```python
from pathlib import Path
from ranker.dataset_io import load_dataset
from ranker.train import train_model
from ranker.evaluate import evaluate

folder = Path("data/ranking_sample")  # use the full dataset for a real evaluation
train = load_dataset(folder / "train.json")
validation = load_dataset(folder / "validation.json")
test = load_dataset(folder / "test.json")

# Optional model-team steps, separate from data preparation:
booster = train_model(
    queries=train,
    validation_queries=validation,
    out_path=Path("models/ranking-data-example.txt"),
)
results = evaluate(queries=test, booster=booster)
```

The loader restores the existing profile/items/place/relevance/features structure.
Compact files store each place once per split and recompute features on loading.
Files with incompatible feature names are rejected: regenerate old raw-price datasets
using current code instead of bypassing the check.
The default `make train` and `make evaluate` commands still use the separate
`ingest.training` dataset already on main. This PR does not switch those commands.
Keep the selected model and its evaluation dataset together when reporting results.

## Validation

Checks cover country/currency consistency, duplicate source IDs, local budgets,
train/test city and full-source place separation, training/validation profile separation,
snapshot checksums, feature preservation and offline reuse. Testing cities are excluded
from both training and validation. Training and validation may share places for different
travelers. Held-out cities do not guarantee every simulated traveler is unseen.

```bash
uv run ruff check .
uv run pytest -q
```

The committed example also has an automated offline CLI rebuild test, and the loader
is tested against the current feature extractor and training/evaluation functions.

## Limits and attribution

Simulated grades test agreement with the project's label formula, not real traveler
satisfaction. OSM coverage, estimated costs and uncertain hours remain limitations.
The sampled source area is not an entire city's complete place inventory. Preparation
checks do not establish recommendation quality or performance in every currency/city.
Snapshots hold ranking inputs, not full application Place records.

Place data © OpenStreetMap contributors, ODbL 1.0:
https://www.openstreetmap.org/copyright
Source attribution and collection metadata are preserved in the example snapshots.
