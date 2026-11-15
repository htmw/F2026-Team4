# Ranking dataset preparation

This prepares training, validation and testing examples from real OpenStreetMap places.
Traveler profiles and suitability grades are simulated using the existing project helpers.

## Dataset

The full dataset is included in `data/ranking_dataset_v3/`.

| File | Contents |
|---|---|
| `train.json` | 4,786 training examples |
| `validation.json` | 1,214 validation examples |
| `test.json` | 1,500 testing examples |
| `manifest.json` | Preparation settings |
| `summary.json` | Counts, cities and source information |

Each example contains one simulated traveler and 15 candidate places.

Training and validation use separate traveler examples from 12 cities.
Tokyo, Bogota and Hyderabad are reserved for testing.

## Train and evaluate

Run from the project root:

```bash
uv sync
uv run python -m ranker.train
uv run python -m ranker.evaluate
```

Training should print `Using v3 dataset.` Evaluation should report
`Evaluating on 1500 v3 unseen-city test queries`.

These commands use v3 when all three split files are present.
Otherwise, they fall back to the older dataset loaded by `ingest.training`.

Run training before evaluation. The trained model is saved to `models/ranker.txt`.

## Prepare a new dataset

Settings are in `ranker/dataset_manifest.json`.

```bash
uv run python -m ranker.prepare_manifest --output data/ranking_dataset_new
```

Use a new output folder because existing folders are not overwritten.
The command reuses saved source snapshots or obtains data through the ingest catalog.
New source data may produce different counts.

A small offline sample is also available:

```bash
uv run python -m ranker.prepare_manifest --manifest ranker/examples/manifest.json --snapshots ranker/examples/snapshots --offline --output data/ranking_sample
```

## Tests

```bash
uv run pytest ranker/tests -q
```

The tests check dataset splitting, duplicate places, currencies, budgets,
feature preservation, snapshot integrity and offline preparation.

## Data source

Place data © OpenStreetMap contributors, ODbL 1.0:
https://www.openstreetmap.org/copyright

Places are real; traveler profiles and suitability grades are simulated.
The evaluation measures agreement with these grades, not real user satisfaction.
