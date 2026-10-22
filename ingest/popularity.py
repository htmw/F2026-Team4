"""Popularity proxy (0..1) built from OSM tags.

OSM has no visitor counts and no review scores. It does carry a strong hint of how well
known a place is: famous places collect translated names, Wikipedia and Wikidata links and
heritage designations, because people all over the world bother to add them. A neighbourhood
cafe has none of that. This module turns those hints into one number between 0 and 1.

It is a proxy, not a measurement, and it is documented as one. The ranker and the scheduler
only use it to order places and to break ties, never as a fact shown to the traveler.
"""

from __future__ import annotations

import math
import re

# name:en, name:fr, name:zh-Hans, name:pt-BR ... but not name:etymology or name:signed.
_NAME_TRANSLATION = re.compile(r"^name:[a-z]{2,3}(?:-[A-Za-z]{2,4})?$")
_SIGHT_TOURISM = {"attraction", "museum", "gallery", "viewpoint"}

# Tags that show someone documented the place properly. Dedupe also uses the count of these
# to decide which of two copies of a place is the richer one.
DOCUMENTATION_KEYS = (
    "wikidata",
    "wikipedia",
    "heritage",
    "website",
    "contact:website",
    "opening_hours",
    "fee",
    "charge",
    "description",
)

# Weights add up to 1.0, so a place that ticks every box scores exactly 1.
WEIGHTS = {
    "names": 0.45,
    "wikidata": 0.15,
    "wikipedia": 0.15,
    "heritage": 0.10,
    "sight": 0.10,
    "documented": 0.05,
}

# A place with this many translated names (or more) gets the full name weight. In Lisbon
# the most translated place, the Belem Tower, has 16, so no Lisbon place gets the full
# weight. That is fine: the score is only used to order places.
NAME_SATURATION = 40


def count_name_translations(tags: dict) -> int:
    return sum(1 for key in tags if _NAME_TRANSLATION.match(key))


def documentation_count(tags: dict) -> int:
    return sum(1 for key in DOCUMENTATION_KEYS if tags.get(key))


def signals_from_tags(tags: dict) -> dict:
    """The tag facts popularity needs, small enough to keep for every place in a run."""
    return {
        "name_translations": count_name_translations(tags),
        "wikidata": tags.get("wikidata") or None,
        "wikipedia": bool(tags.get("wikipedia")),
        "heritage": bool(tags.get("heritage")),
        "sight": tags.get("tourism") in _SIGHT_TOURISM,
        "documented": documentation_count(tags),
    }


def popularity(signals: dict) -> float:
    """Weighted sum of the signals, rounded to 3 decimals. Always within 0..1."""
    names = signals.get("name_translations", 0)
    name_part = min(1.0, math.log1p(names) / math.log1p(NAME_SATURATION))
    documented = min(1.0, signals.get("documented", 0) / len(DOCUMENTATION_KEYS))
    score = (
        WEIGHTS["names"] * name_part
        + WEIGHTS["wikidata"] * bool(signals.get("wikidata"))
        + WEIGHTS["wikipedia"] * bool(signals.get("wikipedia"))
        + WEIGHTS["heritage"] * bool(signals.get("heritage"))
        + WEIGHTS["sight"] * bool(signals.get("sight"))
        + WEIGHTS["documented"] * documented
    )
    return round(min(1.0, max(0.0, score)), 3)
