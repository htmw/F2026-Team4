
"""Constraint-aware Wanderwise itinerary scheduler."""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable
from typing import Any

from optimizer.constraints import (
    budget_allows,
    date_range,
    rest_minutes,
    to_hhmm,
    to_minutes,
    visit_in_windows,
)
from optimizer.scoring import matched_interests, recommendation_reason, score
from optimizer.travel import travel_between

# Known opening hours are a hard constraint (checked in available_visit).
# Inferred or unknown hours are allowed, but a place with verified hours is
# preferred over an otherwise equal place whose hours are only a guess.
HOURS_PENALTY = {"known": 0.0, "inferred": 0.1, "unknown": 0.2}

# Interest mix. Over the trip, each interest should get a share of the stops in
# proportion to its weight (art 0.5 gets about half as many stops as history 1.0).
# A stop that would push an interest past its share is penalized, and so is a second
# stop for the same interest on the same day.
MIX_PENALTY = 0.2
SAME_DAY_PENALTY = 0.08

# Days are filled by the traveler's active hours, not a fixed number of stops. This is
# only a safety cap.
MAX_STOPS_PER_DAY = 10

# Prefer a stop that can start soon. A place that only opens much later (a bar at 18:00)
# is chosen only when nothing closer in time fits, so the afternoon is not skipped.
MAX_PREFERRED_WAIT = 60

# Meals. A food-loving traveler gets lunch and dinner at a restaurant at meal times
# (restaurants may only start at 12:00-14:30 or 19:00-21:30, see constraints.TIME_WINDOWS).
# A meal is a need, not just an interest, so it is not held back by the interest mix.
MEAL_BONUS = 0.25
MEAL_CATEGORIES = {"restaurant"}

# Evenings. When the day runs past 20:00, part of the active time is kept for the
# evening (dinner, a bar), so the plan is not used up by 17:00.
EVENING_START = 18 * 60
EVENING_RESERVE = 150

# Only the best-scoring places are considered for scheduling. A city can have thousands of
# places; no trip needs more than this, and it keeps the travel matrix small (300 places
# = about 90,000 legs).
MAX_CANDIDATES = 300

TravelMatrix = dict | Callable[[list[dict[str, Any]]], dict]


def _shortlist(
    candidates: list[dict[str, Any]],
    quality_of: dict[str, float],
    top_interest_of: dict[str, str],
    limit: int,
) -> list[dict[str, Any]]:
    """The best `limit` places, taken in turn from each interest the traveler has.

    A plain top-N by score can be all one kind: a city has thousands of restaurants, so a
    food lover's top 300 would hold no sights at all and every day would be meals.
    """
    by_interest: dict[str, list[dict[str, Any]]] = {}
    for place in sorted(candidates, key=lambda p: quality_of[p["id"]], reverse=True):
        by_interest.setdefault(top_interest_of[place["id"]], []).append(place)

    picked: list[dict[str, Any]] = []
    queues = list(by_interest.values())
    while queues and len(picked) < limit:
        for queue in queues:
            if queue and len(picked) < limit:
                picked.append(queue.pop(0))
        queues = [queue for queue in queues if queue]

    picked.sort(key=lambda place: quality_of[place["id"]], reverse=True)
    return picked


def schedule(
    places: list[dict[str, Any]],
    profile: dict[str, Any],
    dates: list[str],
    travel_matrix: TravelMatrix | None = None,
    category_map: dict[str, list[str]] | None = None,
    destination: dict[str, Any] | None = None,
    trip_id: str | None = None,
) -> dict[str, Any]:
    """Produce an itinerary matching the existing JSON contract.

    `travel_matrix` is either a ready {(from_id, to_id): {"minutes", "mode"}} dict, or a
    function that builds one for the candidate places (the Data team's travel_legs).
    Without one, travel times are estimated from straight-line distance.
    Pass `trip_id` when re-planning an existing trip so it keeps its id.
    """

    category_map = category_map or {}
    destination = destination or {
        "name": "Unknown",
        "lat": 0.0,
        "lon": 0.0,
    }

    if not dates:
        raise ValueError("At least one travel date is required")

    day_start = to_minutes(profile["day_start"])
    day_end = to_minutes(profile["day_end"])

    if day_end <= day_start:
        raise ValueError("day_end must be after day_start")

    active_minutes = round(
        float(
            profile.get(
                "daily_active_hours",
                (day_end - day_start) / 60,
            )
        ) * 60
    )

    budget = float(profile["budget"]["total"])
    budget_currency = profile["budget"]["currency"]

    # Prices are in the city's own currency (INR in an Indian city), whatever currency the
    # budget was typed in. There is no exchange-rate source, so never convert silently.
    price_currencies = Counter(place["cost"]["currency"] for place in places)
    currency = (
        price_currencies.most_common(1)[0][0] if price_currencies else budget_currency
    )
    budget_applies = budget_currency == currency
    if not budget_applies:
        budget = float("inf")
    walking_limit = int(profile["max_walk_minutes"])
    rest = rest_minutes(float(profile["pace"]))
    evening_reserve = EVENING_RESERVE if day_end >= 20 * 60 else 0
    daytime_minutes = max(0, active_minutes - evening_reserve)
    rejected = set(profile.get("feedback", {}).get("rejected", []))

    # Score every place once. score() already returns 0 for avoided places and
    # for places that match none of the traveler's interests.
    quality_of: dict[str, float] = {}
    skipped_currency = 0
    candidates: list[dict[str, Any]] = []

    for place in places:
        if place["id"] in rejected:
            continue

        # A stray price in another currency cannot be added to the trip total.
        if place["cost"]["currency"] != currency:
            skipped_currency += 1
            continue

        quality = score(place, profile, category_map)
        if quality <= 0:
            continue

        quality_of[place["id"]] = quality
        candidates.append(place)

    # The interest each place serves best, used to keep days varied.
    interest_weights = profile.get("interests", {})
    top_interest_of = {
        place["id"]: max(
            matched_interests(place, category_map),
            key=lambda name: interest_weights.get(name, 0.0),
        )
        for place in candidates
    }

    candidates = _shortlist(candidates, quality_of, top_interest_of, MAX_CANDIDATES)

    # Every interest of the traveler's that each place can count towards.
    positive = {name: float(w) for name, w in interest_weights.items() if float(w) > 0}
    weight_sum = sum(positive.values()) or 1.0
    serves_of = {
        place["id"]: sorted(
            (name for name in matched_interests(place, category_map) if name in positive),
            key=lambda name: -positive[name],
        )
        for place in candidates
    }
    trip_counts: Counter = Counter()
    trip_stops = 0

    def mix_choice(place_id: str, today: Counter) -> tuple[str, float]:
        """The interest this stop counts towards, and the penalty for the mix."""
        def over(name: str) -> float:
            expected = positive[name] / weight_sum * (trip_stops + 1)
            return trip_counts[name] + 1 - expected

        # Count the stop towards whichever of its interests is furthest below its share:
        # a museum can count as art once history already has enough stops.
        serves = min(serves_of[place_id], key=over)
        penalty = MIX_PENALTY * max(0.0, over(serves)) + SAME_DAY_PENALTY * today[serves]
        return serves, penalty

    if callable(travel_matrix):
        travel_matrix = travel_matrix(candidates)

    used: set[str] = set()
    days_out: list[dict[str, Any]] = []
    warnings: list[str] = []
    total_cost = 0.0
    total_walking = 0
    total_quality = 0.0
    estimated_travel = False
    unknown_hours = 0
    unknown_costs = 0

    for day in dates:
        cursor = day_start
        previous = None
        active_used = 0
        items = []
        interests_today: Counter = Counter()
        meals_today: set[str] = set()

        while len(items) < MAX_STOPS_PER_DAY:
            options = []

            for place in candidates:
                if place["id"] in used:
                    continue

                quality = quality_of[place["id"]]
                cost = float(place["cost"]["amount"])

                if not budget_allows(
                    budget - total_cost, cost
                ):
                    continue

                travel, mode, estimated = travel_between(
                    previous,
                    place,
                    walking_limit,
                    travel_matrix,
                )

                if travel < 0:
                    continue

                duration = int(
                    place["typical_duration_minutes"]
                )

                if active_used + travel + duration > active_minutes:
                    continue

                is_meal = bool(place.get("categories")) and set(
                    place["categories"]
                ) <= MEAL_CATEGORIES

                visit = visit_in_windows(
                    place,
                    day,
                    cursor + travel,
                    duration,
                    day_end,
                )

                if visit is None:
                    continue

                start, confidence = visit

                # Daytime stops leave the evening's share of the active time free.
                if start < EVENING_START and (
                    active_used + travel + duration > daytime_minutes
                ):
                    continue

                meal = ("lunch" if start < 17 * 60 else "dinner") if is_meal else None
                if meal in meals_today:
                    continue

                # Prefer high quality, verified hours, a balanced mix of interests,
                # shorter transit and less waiting.
                waiting = start - (cursor + travel)
                serves, mix_penalty = mix_choice(place["id"], interests_today)
                if meal:
                    mix_penalty = -MEAL_BONUS
                utility = (
                    quality
                    - mix_penalty
                    - HOURS_PENALTY.get(confidence, HOURS_PENALTY["unknown"])
                    - 0.0005 * travel
                    - 0.0002 * waiting
                )

                options.append((
                    utility,
                    quality,
                    place,
                    start,
                    duration,
                    cost,
                    travel,
                    mode,
                    confidence,
                    estimated,
                    serves,
                    meal,
                    waiting,
                ))

            if not options:
                break

            # Fill the hours in front of us first; jump ahead to an evening-only place
            # only when nothing that starts soon still fits.
            soon = [o for o in options if o[-1] <= MAX_PREFERRED_WAIT]
            chosen = max(soon or options, key=lambda o: o[0])

            (
                _utility,
                quality,
                place,
                start,
                duration,
                cost,
                travel,
                mode,
                confidence,
                estimated,
                serves,
                meal,
                _waiting,
            ) = chosen

            items.append({
                "place_id": place["id"],
                "name": place["name"],
                "start": to_hhmm(start),
                "end": to_hhmm(start + duration),
                "travel_from_prev": {
                    "minutes": travel,
                    "mode": mode,
                },
                "cost": cost,
                "reason": recommendation_reason(
                    place, profile, category_map
                ),
                "confidence": confidence,
            })

            used.add(place["id"])
            interests_today[serves] += 1
            if meal:
                meals_today.add(meal)
            trip_counts[serves] += 1
            trip_stops += 1
            previous = place
            cursor = start + duration + rest
            active_used += travel + duration + rest
            total_cost += cost
            total_quality += quality

            if mode == "walk":
                total_walking += travel

            if estimated:
                estimated_travel = True

            if confidence != "known":
                unknown_hours += 1

            if place["cost"].get("confidence") != "known":
                unknown_costs += 1

        days_out.append({
            "date": day,
            "items": items,
        })

    placed = sum(len(day["items"]) for day in days_out)

    if estimated_travel:
        warnings.append(
            "Some travel times are estimates; "
            "verify routes before traveling."
        )

    if unknown_hours:
        warnings.append(
            f"Opening hours are unverified for "
            f"{unknown_hours} scheduled place(s)."
        )

    if unknown_costs:
        warnings.append(
            f"Costs are unverified for "
            f"{unknown_costs} scheduled place(s)."
        )

    if not budget_applies:
        warnings.append(
            f"Your budget is in {budget_currency} but prices here are in {currency}, "
            f"so the budget was not applied (no currency conversion yet)."
        )

    if skipped_currency:
        warnings.append(
            f"{skipped_currency} place(s) were skipped because their prices "
            f"are not in {currency}."
        )

    if not placed:
        warnings.append(
            "No attractions fit the selected "
            "dates, budget and travel constraints."
        )

    if placed < len(places):
        warnings.append(
            "Some attractions were omitted because "
            "of preferences or scheduling constraints."
        )

    # Average preference quality of selected visits.
    itinerary_score = (
        round(total_quality / placed, 4)
        if placed else 0.0
    )

    normalized_destination = {
        "name": destination["name"],
        "lat": float(destination["lat"]),
        "lon": float(destination["lon"]),
    }

    if destination.get("country"):
        normalized_destination["country"] = (
            destination["country"]
        )

    return {
        "trip_id": trip_id or str(uuid.uuid4()),
        "destination": normalized_destination,
        "start_date": dates[0],
        "end_date": dates[-1],
        "days": days_out,
        "totals": {
            "cost": round(total_cost, 2),
            "currency": currency,
            "walking_minutes": total_walking,
        },
        "warnings": warnings,
        "score": itinerary_score,
    }


def plan_itinerary(
    profile: dict[str, Any],
    destination: dict[str, Any],
    start_date: str,
    end_date: str,
    city: str | None = None,
    trip_id: str | None = None,
) -> dict[str, Any]:
    """Adapter used by the FastAPI endpoints (same signature as the old stub).

    Places come from the city named in `destination` (or from `city` when given), through
    the Data team's catalog: a committed snapshot, the sample fixtures, or a live
    OpenStreetMap fetch. Raises ingest.catalog.CityNotAvailable when there is no data for
    that city (the API answers 422) and CityFetchFailed when OpenStreetMap is unreachable
    (503). Pass `trip_id` when re-planning.
    """
    from api.contracts import load_categories
    from ingest.catalog import load_city, travel_legs

    # No silent default: a request without a city name is refused, never planned in Lisbon.
    city_data = load_city(city or destination.get("name") or destination.get("city"))
    categories = load_categories()["categories"]
    walking_limit = int(profile["max_walk_minutes"])

    # The city's real name and its country, not however the traveler typed it.
    dest = {
        "name": ", ".join(filter(None, [city_data.name, city_data.country_name])),
        "lat": float(destination.get("lat", city_data.destination["lat"])),
        "lon": float(destination.get("lon", city_data.destination["lon"])),
    }
    country = destination.get("country") or city_data.destination.get("country")
    if country:
        dest["country"] = country

    itinerary = schedule(
        places=city_data.places,
        profile=profile,
        dates=date_range(start_date, end_date),
        # Travel times between the candidates, from the Data team's travel model.
        travel_matrix=lambda candidates: travel_legs(candidates, walking_limit),
        category_map=categories,
        destination=dest,
        trip_id=trip_id,
    )

    if city_data.source == "fixture":
        itinerary["warnings"].append(
            f"Places for {city_data.name} come from the hand-made sample file, not live data."
        )

    return itinerary
