"""A deliberately naive scheduler.

This exists so the whole team has a working end-to-end path on day one. It is
BAD on purpose: it scores places with a simple dot product and packs days
greedily while ignoring travel time and opening hours.

>>> The Optimizer team replaces this. <<<
The real thing lives in /optimizer as pure functions:
    score(place, profile) -> float
    schedule(places, profile, dates, travel_matrix) -> Itinerary
Wire it into /plan (see api/main.py) once it exists. Keep the shapes identical
so nothing else has to change.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from api.contracts import load_categories
from ingest.catalog import load_city


def _get_trained_scorer():
    """Return the trained ranking model's scorer if one has been trained, else None.

    This is the seam between the Lead's API and the Model team's /ranker. When a model
    file exists, the API ranks with it automatically; otherwise it falls back to the
    hand-coded score_place below, so the app works before any model is trained.
    """
    try:
        from ranker.model import get_scorer

        return get_scorer()
    except Exception:
        return None


def _interests_touched(place: dict[str, Any], category_map: dict[str, list[str]]) -> set[str]:
    touched: set[str] = set()
    for category in place.get("categories", []):
        touched.update(category_map.get(category, []))
    return touched


def score_place(
    place: dict[str, Any], profile: dict[str, Any], category_map: dict[str, list[str]]
) -> float:
    """Simple dot product of the place's interests against the traveler's weights.

    TODO(optimizer): waiting for the real score(place, profile). This one rewards places
    that touch many interests and ignores budget fit, popularity, novelty, and confidence.
    """
    weights = profile.get("interests", {})
    return float(sum(weights.get(i, 0.0) for i in _interests_touched(place, category_map)))


def _to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _to_hhmm(minutes: int) -> str:
    minutes = max(0, min(int(minutes), 23 * 60 + 59))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _date_range(start_date: str, end_date: str) -> list[str]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    days = (end - start).days
    if days < 0:
        return [start_date]
    return [(start + timedelta(days=i)).isoformat() for i in range(days + 1)]


def _reason(place: dict[str, Any], profile: dict[str, Any], interests: set[str]) -> str:
    weights = profile.get("interests", {})
    ranked = sorted(interests, key=lambda i: weights.get(i, 0.0), reverse=True)
    if ranked and weights.get(ranked[0], 0.0) > 0:
        return f"Matches your interest in {ranked[0]}."
    return "A popular stop in the city."


def plan_itinerary(
    profile: dict[str, Any],
    destination: dict[str, Any],
    start_date: str,
    end_date: str,
    city: str | None = None,
    trip_id: str | None = None,
) -> dict[str, Any]:
    """Build an Itinerary. Pass `trip_id` when re-planning an existing trip.

    Places come from the city named in `destination` (or from `city` when given). Raises
    ingest.catalog.CityNotAvailable when there is no data for that city.
    """
    category_map = load_categories()["categories"]
    # No silent default: a request without a city name gets a clear 422, not Lisbon.
    city_data = load_city(city or destination.get("name") or destination.get("city"))
    rejected = set(profile.get("feedback", {}).get("rejected", []))
    places = [p for p in city_data.places if p["id"] not in rejected]

    # 1) Score every place, best first. Use the trained ranking model if one exists,
    #    otherwise the hand-coded stub.
    #    TODO(ranker): the model is still trained on synthetic data; waiting for real
    #    Place data from ingest (and real feedback) to retrain it.
    trained_scorer = _get_trained_scorer()

    def _score(place: dict[str, Any]) -> float:
        if trained_scorer is not None:
            return float(trained_scorer(place, profile))
        return score_place(place, profile, category_map)

    scored = sorted(
        ((_score(p), float(p.get("popularity", 0.0)), p) for p in places),
        key=lambda t: (t[0], t[1]),
        reverse=True,
    )
    if trained_scorer is not None:
        ordered = [p for _s, _pop, p in scored]  # trust the model's ranking
    else:
        ordered = [p for s, _pop, p in scored if s > 0]  # stub: keep interest matches only

    # 2) Greedy day packing.
    #    TODO(optimizer): waiting for schedule(places, profile, dates, travel_matrix). This
    #    stub ignores opening hours, travel time, max_walk_minutes and the budget.
    day_start = _to_minutes(profile.get("day_start", "09:00"))
    day_end = _to_minutes(profile.get("day_end", "22:00"))
    pace = float(profile.get("pace", 0.5))
    max_items_per_day = 2 + round(pace * 4)  # relaxed ~2, packed ~6

    dates = _date_range(start_date, end_date)
    used: set[str] = set()
    days_out: list[dict[str, Any]] = []
    total_cost = 0.0
    unverified_hours = 0

    for day_date in dates:
        cursor = day_start
        items: list[dict[str, Any]] = []
        for place in ordered:
            if place["id"] in used:
                continue
            if len(items) >= max_items_per_day:
                break
            duration = int(place["typical_duration_minutes"])
            if cursor + duration > day_end:
                continue

            interests = _interests_touched(place, category_map)
            cost = float(place["cost"]["amount"])
            hours_confidence = place["hours"]["confidence"]
            if hours_confidence != "known":
                unverified_hours += 1

            items.append(
                {
                    "place_id": place["id"],
                    "start": _to_hhmm(cursor),
                    "end": _to_hhmm(cursor + duration),
                    # TODO(ingest, optimizer): waiting for the travel matrix from ingest
                    # and for the optimizer to schedule with it.
                    "travel_from_prev": {"minutes": 0, "mode": "none"},
                    "cost": cost,
                    "reason": _reason(place, profile, interests),
                    "confidence": hours_confidence,
                }
            )
            total_cost += cost
            used.add(place["id"])
            cursor += duration

        days_out.append({"date": day_date, "items": items})

    # 3) Assemble the Itinerary in the contract shape.
    dest = {
        "name": destination.get("name") or city_data.name,
        "lat": float(destination.get("lat", city_data.destination["lat"])),
        "lon": float(destination.get("lon", city_data.destination["lon"])),
    }
    country = destination.get("country") or city_data.destination.get("country")
    if country:
        dest["country"] = country

    # Naive "score": how full the days ended up. Saturates toward 1.0.
    # TODO(optimizer): waiting for a real itinerary quality score.
    placed = sum(len(d["items"]) for d in days_out)
    itinerary_score = round(placed / (placed + 3), 2) if placed else 0.0

    warnings: list[str] = []
    if unverified_hours:
        warnings.append(
            f"Opening hours for {unverified_hours} place(s) could not be verified."
        )
    warnings.append(
        "Stub scheduler: travel time, opening hours and budget are not yet enforced."
    )
    if city_data.source == "fixture":
        warnings.append(
            f"Places for {city_data.name} come from the hand-made sample file, not live data."
        )
    elif city_data.source == "live":
        warnings.append(
            f"Places for {city_data.name} were fetched live from OpenStreetMap and are not "
            "hand checked: most opening hours and prices are estimates."
        )

    currency = profile.get("budget", {}).get("currency", "EUR")
    return {
        "trip_id": trip_id or str(uuid.uuid4()),
        "destination": dest,
        "start_date": start_date,
        "end_date": end_date,
        "days": days_out,
        "totals": {
            "cost": round(total_cost, 2),
            "currency": currency,
            "walking_minutes": 0,
        },
        "warnings": warnings,
        "score": itinerary_score,
    }
