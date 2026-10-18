"""Merge records that describe the same real place.

OSM often maps one sight twice: a node at the entrance plus a polygon for the building, or a
museum node sitting inside an attraction polygon. Left alone, the optimizer could schedule
the same church twice in one day. Two passes find the copies:

1. same wikidata id, closer than 1 km (the distance guard survives a mistyped tag),
2. same normalised name, closer than 60 m.

The copy that knows the most wins. It keeps its id, name and position, borrows known hours
or a known price from a copy when it has none of its own, and picks up any categories the
other copies had. The decision is deterministic, so two runs on the same data agree.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .categories import DEFAULT_DURATION_MIN
from .to_place import normalize_name

SAME_NAME_RADIUS_M = 60.0
SAME_WIKIDATA_RADIUS_M = 1000.0
_TYPE_RANK = {"relation": 2, "way": 1, "node": 0}


@dataclass
class DedupeReport:
    merged: int = 0  # records removed because they were copies
    groups: list[dict] = field(default_factory=list)  # a few examples for the report

    def as_dict(self, max_examples: int = 10) -> dict:
        return {"merged": self.merged, "examples": self.groups[:max_examples]}


def distance_m(a: dict, b: dict) -> float:
    """Great circle distance in metres between two places."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6_371_008.8 * math.asin(math.sqrt(min(1.0, h)))


class _Groups:
    """Tiny union find over list positions."""

    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, i: int, j: int) -> None:
        ri, rj = self.find(i), self.find(j)
        if ri != rj:
            self.parent[max(ri, rj)] = min(ri, rj)


def _richness(place: dict, signals: dict) -> tuple:
    """Sort key: the most useful record of a duplicate group sorts first."""
    s = signals.get(place["id"], {})
    return (
        place["hours"]["confidence"] == "known",
        place["cost"]["confidence"] == "known",
        place.get("popularity", 0.0),
        s.get("documented", 0),
        _TYPE_RANK.get(s.get("osm_type"), 0),
    )


def _merge(group: list[dict], signals: dict) -> dict:
    # Highest richness first; the id breaks ties so the result never depends on input order.
    ordered = sorted(group, key=lambda p: p["id"])
    ordered.sort(key=lambda p: _richness(p, signals), reverse=True)
    winner = dict(ordered[0])
    others = ordered[1:]

    categories = list(winner["categories"])
    for other in others:
        categories += [c for c in other["categories"] if c not in categories]
    winner["categories"] = categories
    winner["typical_duration_minutes"] = max(
        winner["typical_duration_minutes"],
        max(DEFAULT_DURATION_MIN[c] for c in categories),
    )

    if winner["hours"]["confidence"] != "known":
        donor = next((o for o in others if o["hours"]["confidence"] == "known"), None)
        if donor is not None:
            winner["hours"] = donor["hours"]
    if winner["cost"]["confidence"] != "known":
        donor = next((o for o in others if o["cost"]["confidence"] == "known"), None)
        if donor is not None:
            winner["cost"] = donor["cost"]

    winner["popularity"] = max(p.get("popularity", 0.0) for p in group)

    # The winner answers to every name its copies had (useful for curation matching).
    merged_names = set()
    for p in group:
        merged_names.update(signals.get(p["id"], {}).get("names", []))
    if winner["id"] in signals:
        signals[winner["id"]] = {**signals[winner["id"]], "names": sorted(merged_names)}
    return winner


def dedupe(places: list[dict], signals: dict) -> tuple[list[dict], DedupeReport]:
    """Return (places without copies, report). `signals` maps place id to tag facts."""
    groups = _Groups(len(places))

    by_wikidata: dict[str, list[int]] = {}
    for i, p in enumerate(places):
        qid = signals.get(p["id"], {}).get("wikidata")
        if qid:
            by_wikidata.setdefault(qid, []).append(i)
    for members in by_wikidata.values():
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                i, j = members[a], members[b]
                if distance_m(places[i], places[j]) <= SAME_WIKIDATA_RADIUS_M:
                    groups.union(i, j)

    by_name: dict[str, list[int]] = {}
    for i, p in enumerate(places):
        by_name.setdefault(normalize_name(p["name"]), []).append(i)
    for members in by_name.values():
        if len(members) < 2:
            continue
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                i, j = members[a], members[b]
                if distance_m(places[i], places[j]) <= SAME_NAME_RADIUS_M:
                    groups.union(i, j)

    clusters: dict[int, list[dict]] = {}
    for i, p in enumerate(places):
        clusters.setdefault(groups.find(i), []).append(p)

    report = DedupeReport()
    kept: list[dict] = []
    for root in sorted(clusters):
        members = clusters[root]
        if len(members) == 1:
            kept.append(members[0])
            continue
        winner = _merge(members, signals)
        kept.append(winner)
        report.merged += len(members) - 1
        report.groups.append(
            {
                "kept": winner["id"],
                "name": winner["name"],
                "dropped": sorted(p["id"] for p in members if p["id"] != winner["id"]),
            }
        )
    return kept, report
