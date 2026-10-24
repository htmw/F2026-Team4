\# Ranking data from real Rome places



\## Purpose



Prepare training and testing examples using the existing Rome

places collected from OpenStreetMap, including curated details.



The places are real. Traveler profiles are simulated, and suitability

grades are calculated using the existing formula in synthetic.py.

These grades are not ratings or judgments from real travelers.



\## Generate the data



Run from the main project folder:



```powershell

uv run python -m ranker.real\_data

```



Input:



\- data/cities/rome/places.json



Outputs:



\- data/training/rome/train.json

\- data/training/rome/test.json

\- data/training/rome/summary.json



The default run creates 500 simulated traveler examples:



\- 400 for training.

\- 100 for testing.

\- 15 candidate places per traveler.



The entire candidate list for each traveler stays together.

Traveler profiles do not overlap between training and testing.

The same place can appear for different travelers in both sets.



\## Format



Each example uses the existing ranking format:



\- profile: the simulated traveler's preferences.

\- items: candidate places.

\- place: the original place record.

\- relevance: a calculated suitability grade from 0 to 4.

\- features: the existing 11 features in their original order.



No synthetic places are added. The source place records are preserved.



\## Ratings and other limitations



The current Rome source contains 4,549 places and no customer ratings.



Missing ratings remain absent from place records. The existing

feature extractor represents a missing rating as 0. This is a

missing-value convention, not an actual zero-star review.



Existing cost estimates, confidence values and popularity proxies

are preserved. Unknown prices are not verified free entry.



The split supports evaluation on unseen simulated travelers.

It does not measure performance on unseen places, new cities,

or real traveler judgments.



Reproducibility uses seed 42 and the current source files.

Changes to the source data or helper functions can change the output.



\## Tests



Run:



```powershell

uv run python -m pytest ranker/tests/test\_real\_data.py -q

uv run python -m pytest ranker/tests -q

```



Observed locally:



\- 10 new data-preparation tests passed.

\- All 13 tests in ranker/tests passed, including those 10.



The tests check the output format, source-place preservation,

repeatability within a process, traveler separation, matrix

compatibility, missing ratings and invalid source inputs.



These results do not measure the trained model's recommendation quality.



\## Using the prepared data



The model team can pass the training examples to train\_model()

and the testing examples to evaluate():



```python

import json

from pathlib import Path



from ranker.evaluate import evaluate

from ranker.train import train\_model



folder = Path("data/training/rome")

train = json.loads((folder / "train.json").read\_text(encoding="utf-8"))

test = json.loads((folder / "test.json").read\_text(encoding="utf-8"))



booster = train\_model(

&#x20;   queries=train,

&#x20;   out\_path=Path("models/ranker-rome.txt"),

)

results = evaluate(queries=test, booster=booster)

print(results)

```



This example saves a separate model. It has not been run as part

of the data-preparation checks.



The default training and evaluation commands still use synthetic.py

unless the prepared examples are explicitly supplied.



\## Adding real ratings later



Match permitted rating data to the correct source places.

Then regenerate both datasets and retrain the model.

Do not invent ratings for unmatched places.

## Other cities



Rome is the default city. To select a city explicitly:



```powershell

uv run python -m ranker.real\_data --city rome

```



For another city, replace rome with its folder name.

Its collected places must already exist at:



data/cities/<city>/places.json



Outputs are saved separately under:



data/training/<city>/



For a places file stored elsewhere, provide its path:



```powershell

uv run python -m ranker.real\_data --city rome --places "path/to/places.json"

```



This script prepares existing data; it does not download from OSM.

Only Rome has been checked with actual city data so far.

The current simulated profiles use EUR budgets, so other currencies

need handling before preparing data for those cities.

