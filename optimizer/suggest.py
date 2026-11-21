"""Places a traveler could swap in for a stop, or add to a day (GET /trips/{id}/suggestions).

Suggestions are ranked the same way the scheduler ranks places when it plans: the rule score
decides which places qualify, the same shortlist keeps a mix of interests, the trained
ranker's order is used when a model exists, and verified opening hours are preferred.
On top of that, a suggestion should suit the moment it is asked for: open on that day,
near the stop it replaces (or the day's other stops), and indoors when rain is likely.
"""

from __future__ import annotations

from datetime import date as Date
from typing import Any

from optimizer.scheduler import (
    HOURS_PENALTY,
    MAX_CANDIDATES,
    RAIN_OUTDOOR_PENALTY,
    Scorer,
    _ranker_quality,
    _shortlist,
    is_not_a_sight,
)
from optimizer.scoring import matched_interests, recommendation_reason, score
from optimizer.travel import distance_km

MAX_SUGGESTIONS = 5

# A place that is closed all of that day is a poor swap, but still better than nothing
# when every good place is closed (a Monday of closed museums), so it is pushed down, not out.
CLOSED_PENALTY = 0.5

# Being close matters: a little under one tenth of a point per kilometre, up to 0.4 for a
# place 5 km or more away, so a near, slightly weaker place beats a far, slightly better one.
DISTANCE_PENALTY_PER_KM = 0.08
MAX_DISTANCE_PENALTY = 0.4


def _open_on(place: dict[str, Any], day: str) -> bool | None:
    """True or False when the place's hours are verified or estimated; None when unknown."""
    hours = place["hours"]
    if hours.get("confidence") not in ("known", "inferred"):
        return None
    return bool(hours.get(Date.fromisoformat(day).strftime("%a").lower()))


def suggest(
    places: list[dict[str, Any]],
    profile: dict[str, Any],
    itinerary: dict[str, Any],
    category_map: dict[str, list[str]] | None = None,
    scorer: Scorer | None = None,
    replace: str | None = None,
    day: str | None = None,
    limit: int = MAX_SUGGESTIONS,
) -> list[dict[str, Any]]:
    """Up to `limit` places, best first, for swapping out `replace` or adding to `day`.

    Places already in the trip, rejected by the traveler, avoided, closed to visitors
    (a jail, a hospital), priced in another currency or matching none of the traveler's
    interests are left out. Each suggestion
    is {"place_id", "name", "reason", "cost", "cost_confidence"}; `reason` uses the
    scheduler's own wording ("Matches your interest in ..."), which the website reads.
    """
    from ingest.weather import is_outdoor

    category_map = category_map or {}
    by_id = {place["id"]: place for place in places}
    trip_days = itinerary.get("days", [])
    in_trip = {item["place_id"] for d in trip_days for item in d["items"]}
    rejected = set(profile.get("feedback", {}).get("rejected", []))
    currency = itinerary.get("totals", {}).get("currency")

    # The day the suggestion is for: the given one, or the day of the stop being replaced.
    if day is None and replace:
        day = next(
            (d["date"] for d in trip_days if any(i["place_id"] == replace for i in d["items"])),
            None,
        )
    the_day = next((d for d in trip_days if d["date"] == day), None)

    # Where it should be near: the replaced stop, else the middle of that day's stops.
    if replace and replace in by_id:
        anchor = by_id[replace]
    elif the_day and the_day["items"]:
        stops = [by_id[i["place_id"]] for i in the_day["items"] if i["place_id"] in by_id]
        anchor = (
            {"lat": sum(p["lat"] for p in stops) / len(stops),
             "lon": sum(p["lon"] for p in stops) / len(stops)}
            if stops else None
        )
    else:
        anchor = None
    rainy = bool(((the_day or {}).get("weather") or {}).get("rainy"))

    # The same candidates, shortlist and quality as planning (scheduler.schedule).
    quality_of: dict[str, float] = {}
    candidates: list[dict[str, Any]] = []
    for place in places:
        pid = place["id"]
        if pid in in_trip or pid in rejected or pid == replace:
            continue
        if is_not_a_sight(place):  # never offer a jail or a hospital as a swap
            continue
        if currency and place["cost"]["currency"] != currency:
            continue
        quality = score(place, profile, category_map)
        if quality <= 0:
            continue
        quality_of[pid] = quality
        candidates.append(place)

    if not candidates:
        return []

    weights = profile.get("interests", {})
    top_interest_of = {
        place["id"]: max(
            matched_interests(place, category_map),
            key=lambda name: weights.get(name, 0.0),
        )
        for place in candidates
    }
    candidates = _shortlist(candidates, quality_of, top_interest_of, MAX_CANDIDATES)
    if scorer is not None:
        quality_of.update(_ranker_quality(candidates, profile, scorer))

    def fit(place: dict[str, Any]) -> float:
        value = quality_of[place["id"]]
        value -= HOURS_PENALTY.get(place["hours"].get("confidence"), HOURS_PENALTY["unknown"])
        if day and _open_on(place, day) is False:
            value -= CLOSED_PENALTY
        if anchor is not None:
            km = distance_km(anchor, place)
            value -= min(MAX_DISTANCE_PENALTY, DISTANCE_PENALTY_PER_KM * km)
        if rainy and is_outdoor(place):
            value -= RAIN_OUTDOOR_PENALTY
        return value

    best = sorted(candidates, key=lambda place: (-fit(place), place["id"]))[:limit]
    return [
        {
            "place_id": place["id"],
            "name": place["name"],
            "reason": recommendation_reason(place, profile, category_map),
            "cost": float(place["cost"]["amount"]),
            "cost_confidence": place["cost"]["confidence"],
        }
        for place in best
    ]


def suggest_for_trip(
    request: dict[str, Any],
    itinerary: dict[str, Any],
    replace: str | None = None,
    day: str | None = None,
) -> list[dict[str, Any]]:
    """Adapter for the API: the trip's city, the team's categories and the trained ranker,
    exactly as plan_itinerary() uses them. Raises the same catalog errors as planning."""
    from api.contracts import load_categories
    from ingest.catalog import load_city
    from ranker.model import get_scorer

    destination = request["destination"]
    city_data = load_city(destination.get("name") or destination.get("city"))
    return suggest(
        places=city_data.places,
        profile=request["profile"],
        itinerary=itinerary,
        category_map=load_categories()["categories"],
        scorer=get_scorer(),
        replace=replace,
        day=day,
    )
