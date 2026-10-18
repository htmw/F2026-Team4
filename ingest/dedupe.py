"""Merge records that describe the same real place.

OSM often maps one sight twice: a node at the entrance plus a polygon for the building, or a
museum node sitting inside an attraction polygon. Left alone, the optimizer could schedule
the same church twice in one day.

Long structures first. City walls and aqueducts are mapped as many short pieces that share
a name: Lisbon has 36 pieces of the Aguas Livres aqueduct. Every record that shares a name or
a wikidata id with such a piece is the same structure, wherever it is in the city, so the
group becomes one stop. Gates and towers have names of their own and stay separate. The
stop is placed on its best node or way. A relation only has the centre of its bounding box,
which for a ring of walls is the middle of the city, so it is used for the position only
when it is a single area (a multipolygon) and nothing better exists. A structure that has
neither cannot be placed and is dropped.

Then everything else. Records are visited from the richest to the poorest. Each record that
is not yet taken becomes a seed, and only records close to that seed can join it, so a
chain of neighbours can never stretch a group across a city:

1. same wikidata id: within 1 km of the seed when the names match, within 100 m when they
   do not (two different fountains of one square share an id and must stay two stops),
2. same normalised name within 60 m of the seed, unless the two carry different wikidata
   ids.

A venue (restaurant, bar, shop...) never joins a sight or the other way round, in any pass.
A museum cafe tagged with the museum's wikidata must not swallow the museum.

The richest record wins. It keeps its id and name, borrows known hours or a known price from
a copy when it has none of its own, and picks up any categories the copies had. The order is
fixed (richness, then id), so two runs on the same data agree.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .categories import DEFAULT_DURATION_MIN, FREE_BY_DEFAULT, most_specific_first
from .to_place import default_hours, normalize_name

SAME_NAME_RADIUS_M = 60.0
SAME_WIKIDATA_RADIUS_M = 1000.0
SAME_WIKIDATA_OTHER_NAME_RADIUS_M = 100.0
VENUE_CATEGORIES = {"restaurant", "cafe", "bakery", "bar", "nightclub", "shop"}
_TYPE_RANK = {"relation": 2, "way": 1, "node": 0}


@dataclass
class DedupeReport:
    merged: int = 0  # records removed because they were copies
    groups: list[dict] = field(default_factory=list)  # a few examples for the report
    long_structures: list[dict] = field(default_factory=list)
    no_position: list[str] = field(default_factory=list)  # dropped: no point on the structure

    def as_dict(self, max_examples: int = 10) -> dict:
        return {
            "merged": self.merged,
            "examples": self.groups[:max_examples],
            "long_structures": self.long_structures,
            "dropped_no_position": self.no_position,
        }


def distance_m(a: dict, b: dict) -> float:
    """Great circle distance in metres between two places."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6_371_008.8 * math.asin(math.sqrt(min(1.0, h)))


def is_venue(place: dict) -> bool:
    return place["categories"][0] in VENUE_CATEGORIES


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


def _names(place: dict, signals: dict) -> set[str]:
    return set(signals.get(place["id"], {}).get("names") or []) | {normalize_name(place["name"])}


def merge_group(group: list[dict], signals: dict) -> dict:
    """Fold copies into one record. group[0] wins; the rest are its copies.

    Curation uses this too, for the copies it finds around a curated place.
    """
    winner = dict(group[0])
    others = group[1:]

    categories = list(winner["categories"])
    for other in others:
        categories += [c for c in other["categories"] if c not in categories]
    categories = most_specific_first(categories)
    new_primary = categories[0] != winner["categories"][0]
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

    # A copy can bring a more specific category: the Jeronimos Monastery is a landmark in
    # one record and a museum in another. Defaults that came from the old primary category
    # (open all day, free entry) are then wrong, so they follow the new one.
    if new_primary:
        if winner["hours"]["confidence"] == "inferred":
            winner["hours"] = default_hours(categories[0])
        if winner["cost"]["confidence"] == "inferred" and categories[0] not in FREE_BY_DEFAULT:
            winner["cost"] = {**winner["cost"], "confidence": "unknown"}

    winner["popularity"] = max(p.get("popularity", 0.0) for p in group)

    # The winner answers to every name its copies had (useful for curation matching).
    merged_names = set()
    for p in group:
        merged_names.update(signals.get(p["id"], {}).get("names", []))
    if winner["id"] in signals:
        signals[winner["id"]] = {**signals[winner["id"]], "names": sorted(merged_names)}
    return winner


class _Keys:
    """Puts keys that belong to the same structure into one group (a small union-find).

    The keys are names (name:cerca moura) and wikidata ids (qid:Q123). If one wall piece
    carries a name and an id, and another piece carries a second name and the same id,
    union() links all three, and find() returns the same group label for each of them.
    """

    def __init__(self):
        self.parent: dict[str, str] = {}

    def add(self, key: str) -> None:
        self.parent.setdefault(key, key)

    def find(self, key: str) -> str:
        while self.parent[key] != key:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]
        return key

    def union(self, a: str, b: str) -> None:
        self.add(a)
        self.add(b)
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _long_structures(places: list[dict], signals: dict, order: list[int]) -> list[list[int]]:
    """Groups of indices that are one wall or aqueduct, each in richness order.

    First pass: collect the names and wikidata ids of every wall or aqueduct piece and link
    the ones that belong together. Second pass: every sight that carries one of those names
    or ids joins its structure, wherever it is in the city. Venues and neighbourhoods never
    join.
    """

    def facts(i):
        return signals.get(places[i]["id"], {})

    keys = _Keys()
    for i in order:
        if facts(i).get("long_structure") and not is_venue(places[i]):
            name_key = "name:" + normalize_name(places[i]["name"])
            keys.add(name_key)
            if facts(i).get("wikidata"):
                keys.union(name_key, "qid:" + facts(i)["wikidata"])

    groups: dict[str, list[int]] = {}
    for i in order:
        if is_venue(places[i]) or places[i]["categories"][0] == "neighborhood":
            continue
        name_key = "name:" + normalize_name(places[i]["name"])
        qid = facts(i).get("wikidata")
        if name_key in keys.parent:
            root = keys.find(name_key)
        elif qid and "qid:" + qid in keys.parent:
            root = keys.find("qid:" + qid)
        else:
            continue
        groups.setdefault(root, []).append(i)
    return list(groups.values())


def dedupe(places: list[dict], signals: dict) -> tuple[list[dict], DedupeReport]:
    """Return (places without copies, report). `signals` maps place id to tag facts."""
    order = sorted(range(len(places)), key=lambda i: places[i]["id"])
    order.sort(key=lambda i: _richness(places[i], signals), reverse=True)
    report = DedupeReport()
    taken = [False] * len(places)
    kept: list[dict] = []

    def qid(i: int) -> str | None:
        return signals.get(places[i]["id"], {}).get("wikidata")

    def facts(i: int) -> dict:
        return signals.get(places[i]["id"], {})

    for members in _long_structures(places, signals, order):
        for i in members:
            taken[i] = True
        # A node or a way lies on the structure. A relation only has the centre of its
        # bounding box: usable for a single area (a multipolygon), never for a collection.
        anchor = next((i for i in members if facts(i).get("osm_type") != "relation"), None)
        if anchor is None:
            anchor = next((i for i in members if not facts(i).get("rough_point")), None)
        if anchor is None:
            report.no_position.extend(places[i]["id"] for i in members)
            continue
        winner = merge_group([places[i] for i in members], signals)
        winner["lat"], winner["lon"] = places[anchor]["lat"], places[anchor]["lon"]
        kept.append(winner)
        report.merged += len(members) - 1
        report.long_structures.append(
            {
                "kept": winner["id"],
                "name": winner["name"],
                "pieces": len(members),
                "placed_at": places[anchor]["id"],
            }
        )

    by_qid: dict[str, list[int]] = {}
    by_name: dict[str, list[int]] = {}
    for i in order:  # index lists are in richness order too
        if taken[i]:
            continue
        if qid(i):
            by_qid.setdefault(qid(i), []).append(i)
        by_name.setdefault(normalize_name(places[i]["name"]), []).append(i)

    for i in order:
        if taken[i]:
            continue
        taken[i] = True
        seed = places[i]
        seed_names = _names(seed, signals)
        members = [i]
        qids = {qid(i)} if qid(i) else set()

        for j in by_qid.get(qid(i), []) if qid(i) else []:
            if taken[j] or is_venue(places[j]) != is_venue(seed):
                continue
            same_name = bool(seed_names & _names(places[j], signals))
            limit = SAME_WIKIDATA_RADIUS_M if same_name else SAME_WIKIDATA_OTHER_NAME_RADIUS_M
            if distance_m(seed, places[j]) <= limit:
                taken[j] = True
                members.append(j)

        for j in by_name[normalize_name(seed["name"])]:
            if taken[j] or distance_m(seed, places[j]) > SAME_NAME_RADIUS_M:
                continue
            other_qid = qid(j)
            if other_qid and qids and other_qid not in qids:
                continue  # two different Wikidata items that happen to share a name
            if is_venue(places[j]) != is_venue(seed):
                continue  # a bar named after a palace is not the palace
            taken[j] = True
            members.append(j)
            if other_qid:
                qids.add(other_qid)

        group = [places[m] for m in members]
        if len(group) == 1:
            kept.append(seed)
            continue
        winner = merge_group(group, signals)
        kept.append(winner)
        report.merged += len(group) - 1
        report.groups.append(
            {
                "kept": winner["id"],
                "name": winner["name"],
                "dropped": sorted(p["id"] for p in group[1:]),
            }
        )

    kept.sort(key=lambda p: p["id"])
    return kept, report
