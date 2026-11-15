"""A short "what is this place" line for every place.

Famous places (an OSM wikidata or wikipedia tag) get the first sentences of their English
Wikipedia article. Every other place gets a line built from its OSM tags, such as
"Restaurant serving Hyderabadi and biryani food." Wikipedia text is CC BY-SA, so each
description says where it came from and the website names Wikipedia next to it.

Saved as descriptions.json next to places.json ({place_id: {"text", "source"}}), not inside
the place records, so every place still matches contracts/place.schema.json.
"""

from __future__ import annotations

import re

import requests

from .geocode import USER_AGENT

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": USER_AGENT}
WIKIDATA_BATCH = 50  # the most ids wbgetentities takes in one request
WIKIPEDIA_BATCH = 20  # the most intros prop=extracts returns in one request
MAX_WIKI_PLACES = 500  # the most popular famous places of a city; a trip needs far fewer
MAX_CHARS = 280

KIND = {
    "restaurant": "Restaurant",
    "cafe": "Café",
    "bakery": "Bakery",
    "bar": "Bar",
    "nightclub": "Nightclub",
    "museum": "Museum",
    "gallery": "Art gallery",
    "palace": "Palace",
    "castle": "Castle or fort",
    "church": "Church",
    "landmark": "Landmark",
    "monument": "Monument",
    "viewpoint": "Viewpoint",
    "park": "Park",
    "garden": "Garden",
    "beach": "Beach",
    "market": "Market",
    "shop": "Shop",
    "neighborhood": "Neighbourhood",
    "day_trip": "Day trip",
}
RELIGION = {
    "hindu": "Hindu temple",
    "muslim": "Mosque",
    "buddhist": "Buddhist temple",
    "jain": "Jain temple",
    "sikh": "Gurdwara",
    "jewish": "Synagogue",
    "shinto": "Shinto shrine",
    "taoist": "Taoist temple",
    "christian": "Church",
}
HISTORIC = {
    "ruins": "Historic ruins",
    "archaeological_site": "Archaeological site",
    "city_gate": "Historic city gate",
    "tower": "Historic tower",
    "fort": "Fort",
    "monastery": "Monastery",
    "citywalls": "Historic city walls",
    "aqueduct": "Historic aqueduct",
    "memorial": "Memorial",
}
_LATIN = re.compile(r"^[\x00-ɏḀ-ỿ -⁯\s]+$")


def _words(value: str) -> str:
    """'indian;biryani' -> 'Indian and biryani'; 'fast_food' -> 'fast food'."""
    parts = [p.strip().replace("_", " ") for p in value.split(";") if p.strip()]
    if not parts:
        return ""
    parts[0] = parts[0][:1].upper() + parts[0][1:]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _year(start_date: str) -> str:
    match = re.match(r"^\s*~?(\d{3,4})", start_date or "")
    return match.group(1) if match else ""


def describe_from_tags(tags: dict, categories: list[str]) -> str:
    """One line from the place's OSM tags. Uses the OSM description when it is readable."""
    own = (tags.get("description:en") or tags.get("description") or "").strip()
    if own and _LATIN.match(own) and len(own) > 15:
        return _short(own)

    kind = categories[0] if categories else ""
    label = KIND.get(kind, "Place")
    if tags.get("amenity") == "place_of_worship":
        label = RELIGION.get(tags.get("religion", ""), "Place of worship")
    elif tags.get("historic") in HISTORIC and kind in ("landmark", "monument", "castle", ""):
        label = HISTORIC[tags["historic"]]

    line = label
    cuisine = _words(tags.get("cuisine", ""))
    if cuisine and kind in ("restaurant", "cafe", "bakery", "bar"):
        line += f" serving {cuisine[:1].lower() + cuisine[1:]} food"
    year = _year(tags.get("start_date", ""))
    if year:
        line += f", built in {year}"
    return line + "."


def _short(text: str) -> str:
    """At most MAX_CHARS, cut at the end of a sentence when there is one."""
    text = " ".join(text.split())
    if len(text) <= MAX_CHARS:
        return text
    cut = text[:MAX_CHARS]
    end = cut.rfind(". ")
    return cut[: end + 1] if end > 80 else cut.rsplit(" ", 1)[0] + "…"


def _dict(payload) -> dict:
    """The answer when it is the JSON object asked for; an empty one otherwise."""
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected answer: {type(payload).__name__}")
    return payload


def _wikidata_titles(ids: list[str], get, log) -> dict[str, str]:
    """{wikidata id: English Wikipedia title} for the ids that have an English article."""
    titles: dict[str, str] = {}
    for start in range(0, len(ids), WIKIDATA_BATCH):
        batch = ids[start:start + WIKIDATA_BATCH]
        try:
            resp = get(
                WIKIDATA_API,
                params={
                    "action": "wbgetentities",
                    "ids": "|".join(batch),
                    "props": "sitelinks",
                    "sitefilter": "enwiki",
                    "format": "json",
                },
                headers=HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            entities = _dict(resp.json()).get("entities") or {}
        except (requests.RequestException, ValueError) as exc:
            log(f"  descriptions: Wikidata unavailable ({exc}); using OSM lines")
            return titles
        for qid, entity in entities.items():
            title = ((entity.get("sitelinks") or {}).get("enwiki") or {}).get("title")
            if title:
                titles[qid] = title
    return titles


def _wikipedia_intros(titles: list[str], get, log) -> dict[str, str]:
    """{title: first sentences} from English Wikipedia, following redirects."""
    intros: dict[str, str] = {}
    for start in range(0, len(titles), WIKIPEDIA_BATCH):
        batch = titles[start:start + WIKIPEDIA_BATCH]
        try:
            resp = get(
                WIKIPEDIA_API,
                params={
                    "action": "query",
                    "prop": "extracts",
                    "exintro": 1,
                    "explaintext": 1,
                    "exsentences": 2,
                    "redirects": 1,
                    "titles": "|".join(batch),
                    "format": "json",
                },
                headers=HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            query = _dict(resp.json()).get("query") or {}
        except (requests.RequestException, ValueError) as exc:
            log(f"  descriptions: Wikipedia unavailable ({exc}); using OSM lines")
            return intros
        # A redirected title answers under its target's name: map it back.
        back = {r["to"]: r["from"] for r in query.get("redirects", [])}
        back.update({n["to"]: n["from"] for n in query.get("normalized", [])})
        for page in (query.get("pages") or {}).values():
            text = (page.get("extract") or "").strip()
            if text and "may refer to" not in text:
                title = page.get("title", "")
                intros[back.get(title, title)] = _short(text)
    return intros


def describe_places(
    places: list[dict],
    info: dict[str, dict],
    *,
    wikipedia: bool = True,
    get=requests.get,
    log=print,
) -> dict[str, dict]:
    """{place_id: {"text", "source"}} for every place.

    info holds what the OSM element said about each place id: {"tags": {...}}. Wikipedia is
    asked only for famous places, most popular first, and any failure falls back to the
    line built from the tags, so a description never stops a city from loading.
    """
    out: dict[str, dict] = {}
    famous: dict[str, str] = {}  # place id -> English Wikipedia title or wikidata id
    for place in places:
        tags = (info.get(place["id"]) or {}).get("tags") or {}
        out[place["id"]] = {
            "text": describe_from_tags(tags, place.get("categories") or []),
            "source": "openstreetmap",
        }
        wiki = tags.get("wikipedia") or ""
        if wiki.startswith("en:"):
            famous[place["id"]] = "title:" + wiki[3:]
        elif re.fullmatch(r"Q\d+", tags.get("wikidata") or ""):
            famous[place["id"]] = tags["wikidata"]

    if not wikipedia or not famous:
        return out

    popularity = {p["id"]: float(p.get("popularity") or 0) for p in places}
    by_popularity = sorted(famous, key=lambda pid: -popularity[pid])
    famous = {pid: famous[pid] for pid in by_popularity[:MAX_WIKI_PLACES]}
    qids = sorted({ref for ref in famous.values() if not ref.startswith("title:")})
    qid_titles = _wikidata_titles(qids, get, log) if qids else {}
    title_of = {
        pid: ref[6:] if ref.startswith("title:") else qid_titles.get(ref)
        for pid, ref in famous.items()
    }
    intros = _wikipedia_intros(sorted({t for t in title_of.values() if t}), get, log)
    for pid, title in title_of.items():
        if title and title in intros:
            out[pid] = {"text": intros[title], "source": "wikipedia"}
    log(f"  descriptions: {sum(d['source'] == 'wikipedia' for d in out.values())} from Wikipedia")
    return out

