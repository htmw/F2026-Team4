\# Ranking training data



This pipeline prepares ranking examples from real OpenStreetMap places

using the project's existing feature extraction and suitability formula.



It runs separately from the application. It does not train the model.



\## Data sources



\- Places: OpenStreetMap records collected through the existing live catalog.

\- Traveler profiles: simulated.

\- Suitability grades: simulated integers from 0 to 4, calculated using

&#x20; the existing ranking-data formula.

\- Ratings: existing ratings are preserved when supplied. Missing ratings

&#x20; are not invented; the existing feature code encodes them as zero.

&#x20; This does not represent a real zero-star rating.



\## Dataset splits



| Split | Traveler examples | Purpose |

|---|---:|---|

| Training | 4,786 | Train the ranking model |

| Validation | 1,214 | Tune settings and compare model versions |

| Testing | 1,500 | Final evaluation on reserved cities |



Each traveler example contains 15 candidate places.



Training and validation use 12 cities:

Paris, Lisbon, Berlin, New York, Los Angeles, Mexico City, Singapore,

Delhi, Mumbai, Cairo, Sydney and Melbourne.



Testing uses three separate cities:

Tokyo, Bogota and Hyderabad.



Up to 500 places are sampled per city. Smaller sources retain all places.

Training and validation profiles are separated.

Full source place IDs are checked for overlap between the

training/development and testing city groups.



City selection, sampling settings and simulation budgets are configured

in `ranker/dataset\_manifest.json`.



\## Prepare the dataset



From the project root:



```bash

uv run python -m ranker.prepare\_manifest

```



The command reuses saved ranking snapshots when available. For missing

snapshots, it calls the existing live catalog, which may reuse its cache

or fetch data from OpenStreetMap.



Default outputs:



\- `data/ranking\_dataset\_v3/`: training, validation, testing, manifest

&#x20; and summary files.

\- `data/ranking\_sources\_v3/`: compact source snapshots, metadata,

&#x20; source IDs and checksums.



Existing output folders are not overwritten.



\## Rebuild without downloading



With the included source snapshots available:



```bash

uv run python -m ranker.prepare\_manifest --offline --output data/ranking\_dataset\_rebuilt

```



Offline mode requires saved snapshots and does not fetch missing cities.

Use a new output folder.



Exact reproduction requires the same snapshots, manifest, code and

dependencies. The preparation command fixes Python's hash seed for

consistent feature and label generation.



\## Prepare a fresh snapshot collection



```bash

uv run python -m ranker.prepare\_manifest --snapshots data/ranking\_sources\_fresh --output data/ranking\_dataset\_fresh

```



This uses the existing live catalog and its cache policy.

It does not force a fresh network download.

Changed OpenStreetMap data can produce different datasets.



\## Load examples for the model



```python

from pathlib import Path

from ranker.dataset\_io import load\_dataset



folder = Path("data/ranking\_dataset\_v3")



train\_queries = load\_dataset(folder / "train.json")

validation\_queries = load\_dataset(folder / "validation.json")

test\_queries = load\_dataset(folder / "test.json")

```



The loader restores the existing query structure:



\- Traveler profile.

\- Candidate place details.

\- Suitability grade.

\- Feature vector in the existing model's feature order.



Pass these queries explicitly to the model's training and evaluation

functions. Default model commands still use synthetic data.



Use validation for tuning. Reserve testing for final evaluation.



\## Storage and validation



Places are stored once per split file and referenced by ID.

Features are reconstructed when loading.



Preparation checks include:



\- Unique city keys and separate training/testing city lists.

\- Country and currency matching.

\- Duplicate source place IDs.

\- Valid simulation budgets.

\- Training/testing source place separation.

\- Training/validation profile separation.

\- Snapshot configuration and file checksums.

\- Feature preservation during compact storage.



Snapshots contain ranking inputs, not complete application Place records.



\## Tests



```bash

uv run python -m pytest ranker/tests/test\_dataset\_io.py ranker/tests/test\_prepare\_live.py ranker/tests/test\_prepare\_dataset.py ranker/tests/test\_prepare\_manifest.py -q

```



Run the full project suite with:



```bash

uv run python -m pytest -q

```



Local verification completed:



\- Full project suite: 290 passed, with two dependency deprecation warnings.

\- Offline rebuild: all five dataset output files matched byte for byte.



\## Limitations



\- Traveler profiles and suitability grades are simulated, not collected

&#x20; from real travelers.

\- Real review ratings are unavailable in the current sources.

\- Budgets are explicit simulation settings in each city's currency,

&#x20; not exchange rates or verified travel-cost estimates.

\- Existing inferred costs and popularity estimates are retained.

\- Raw price features remain in local currency; cross-currency model

&#x20; performance needs evaluation.

\- Training and validation can contain the same places for different

&#x20; travelers.

\- Reserved-city testing does not guarantee that every traveler profile

&#x20; is unseen.

\- Sampled places represent the areas returned by the live catalog,

&#x20; not every place in an entire city.

\- Passing preparation tests does not establish recommendation quality.

&#x20; Model training and evaluation are separate work.



\## Attribution



Place data: © OpenStreetMap contributors, licensed under ODbL 1.0.



https://www.openstreetmap.org/copyright



Source attribution and provenance are retained in snapshot metadata.

