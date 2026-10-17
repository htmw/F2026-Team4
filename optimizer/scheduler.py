
"""Constraint-aware Wanderwise itinerary scheduler."""

from __future__ import annotations

import uuid
from typing import Any

from optimizer.constraints import (
    available_visit,
    budget_allows,
    date_range,
    max_stops,
    to_hhmm,
    to_minutes,
)
from optimizer.scoring import score, recommendation_reason
from optimizer.travel import travel_between


def schedule(
    places: list[dict[str, Any]],
    profile: dict[str, Any],
    dates: list[str],
    travel_matrix: dict | None = None,
    category_map: dict[str, list[str]] | None = None,
    destination: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Produce an itinerary matching the existing JSON contract."""

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
    currency = profile["budget"]["currency"]
    walking_limit = int(profile["max_walk_minutes"])
    stop_limit = max_stops(float(profile["pace"]))

    ranked = sorted(
        places,
        key=lambda place: score(
            place, profile, category_map
        ),
        reverse=True,
    )

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

        while len(items) < stop_limit:
            options = []

            for place in ranked:
                if place["id"] in used:
                    continue

                quality = score(
                    place, profile, category_map
                )

                # Exclude explicitly avoided attractions.
                if place["id"] in profile.get("avoid", []):
                    continue

                if set(place["categories"]) & set(
                    profile.get("avoid", [])
                ):
                    continue

                if quality <= 0:
                    continue

                cost_info = place["cost"]

                # Do not silently convert currencies.
                if cost_info["currency"] != currency:
                    continue

                cost = float(cost_info["amount"])

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

                visit = available_visit(
                    place,
                    day,
                    cursor + travel,
                    duration,
                    day_end,
                )

                if visit is None:
                    continue

                start, confidence = visit

                # Prefer high quality, shorter transit and less waiting.
                waiting = start - (cursor + travel)
                utility = (
                    quality
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
                ))

            if not options:
                break

            chosen = max(options, key=lambda o: o[0])

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
            ) = chosen

            items.append({
                "place_id": place["id"],
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
            previous = place
            cursor = start + duration
            active_used += travel + duration
            total_cost += cost
            total_quality += quality

            if mode == "walk":
                total_walking += travel

            if estimated:
                estimated_travel = True

            if confidence != "known":
                unknown_hours += 1

            if cost_info := place.get("cost"):
                if cost_info.get("confidence") != "known":
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
        "trip_id": str(uuid.uuid4()),
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
    city: str = "lisbon",
) -> dict[str, Any]:
    """Adapter used by the existing FastAPI endpoint."""
    from api.contracts import load_categories, load_places

    places = load_places(city)
    categories = load_categories()["categories"]

    return schedule(
        places=places,
        profile=profile,
        dates=date_range(start_date, end_date),
        category_map=categories,
        destination={
            "name": destination.get(
                "name", city.title()
            ),
            "lat": destination.get("lat", 38.7223),
            "lon": destination.get("lon", -9.1393),
            **({
                "country": destination["country"]
            } if destination.get("country") else {}),
        },
    )
