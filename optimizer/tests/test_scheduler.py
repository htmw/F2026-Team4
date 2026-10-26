
"""Automated tests for the itinerary scheduler."""

from copy import deepcopy

from api.contracts import validate
from optimizer.scheduler import schedule

HOURS = {
    day: [["09:00", "18:00"]]
    for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
}
HOURS["confidence"] = "known"


def make_place(
    place_id,
    cost=10,
    duration=60,
    hours=None,
):
    return {
        "id": place_id,
        "name": f"Place {place_id}",
        "lat": 38.72,
        "lon": -9.14,
        "categories": ["museum"],
        "typical_duration_minutes": duration,
        "cost": {
            "amount": cost,
            "currency": "EUR",
            "confidence": "known",
        },
        "hours": deepcopy(hours or HOURS),
        "rating": 4.5,
        "popularity": 0.8,
        "source": "fixture",
    }


PROFILE = {
    "interests": {"history": 1.0},
    "pace": 0.5,
    "max_walk_minutes": 20,
    "daily_active_hours": 6,
    "day_start": "09:00",
    "day_end": "18:00",
    "budget": {
        "total": 100,
        "currency": "EUR",
    },
}

DESTINATION = {
    "name": "Lisbon",
    "lat": 38.7223,
    "lon": -9.1393,
    "country": "Portugal",
}

CATEGORIES = {"museum": ["history"]}


def run(places, profile=None, dates=None, matrix=None):
    return schedule(
        places=places,
        profile=profile or PROFILE,
        dates=dates or ["2026-10-19"],
        travel_matrix=matrix,
        category_map=CATEGORIES,
        destination=DESTINATION,
    )


def test_itinerary_contract():
    result = run([make_place("museum-1")])
    assert validate("itinerary", result) == []


def test_budget_is_enforced():
    profile = deepcopy(PROFILE)
    profile["budget"]["total"] = 15

    result = run(
        [make_place("a", cost=10),
         make_place("b", cost=10)],
        profile,
    )

    assert result["totals"]["cost"] <= 15


def test_closed_places_are_excluded():
    closed = deepcopy(HOURS)
    closed["mon"] = None

    result = run([
        make_place("closed", hours=closed)
    ])

    assert not result["days"][0]["items"]


def test_opening_hours_are_respected():
    late = deepcopy(HOURS)
    late["mon"] = [["12:00", "14:00"]]

    result = run([
        make_place("late", hours=late)
    ])

    item = result["days"][0]["items"][0]
    assert item["start"] >= "12:00"
    assert item["end"] <= "14:00"


def test_no_duplicate_attractions():
    result = run(
        [make_place("a"), make_place("b")],
        dates=["2026-10-19", "2026-10-20"],
    )

    ids = [
        item["place_id"]
        for day in result["days"]
        for item in day["items"]
    ]

    assert len(ids) == len(set(ids))


def test_avoided_place_not_selected():
    profile = deepcopy(PROFILE)
    profile["avoid"] = ["a"]

    result = run(
        [make_place("a"), make_place("b")],
        profile,
    )

    ids = [
        item["place_id"]
        for day in result["days"]
        for item in day["items"]
    ]

    assert "a" not in ids


def test_walking_limit():
    profile = deepcopy(PROFILE)
    profile["max_walk_minutes"] = 10

    matrix = {
        ("a", "b"): {
            "minutes": 45,
            "mode": "walk",
        },
        ("b", "a"): {
            "minutes": 45,
            "mode": "walk",
        },
    }

    result = run(
        [make_place("a"), make_place("b")],
        profile,
        matrix=matrix,
    )

    assert len(result["days"][0]["items"]) == 1


def test_multi_day_schedule():
    result = run(
        [make_place(str(i)) for i in range(8)],
        dates=["2026-10-19", "2026-10-20"],
    )

    assert len(result["days"]) == 2
    assert result["start_date"] == "2026-10-19"
    assert result["end_date"] == "2026-10-20"


def _ids(result):
    return [
        item["place_id"]
        for day in result["days"]
        for item in day["items"]
    ]


def test_rejected_place_not_selected():
    profile = deepcopy(PROFILE)
    profile["feedback"] = {"accepted": [], "rejected": ["a"]}

    result = run(
        [make_place("a"), make_place("b")],
        profile,
    )

    assert "a" not in _ids(result)
    assert "b" in _ids(result)


def test_trip_id_is_kept_when_replanning():
    result = schedule(
        places=[make_place("a")],
        profile=PROFILE,
        dates=["2026-10-19"],
        category_map=CATEGORIES,
        destination=DESTINATION,
        trip_id="trip-123",
    )

    assert result["trip_id"] == "trip-123"


def test_strongest_interest_wins():
    # A traveler who loves food should get the restaurant before a palace that
    # matches two weaker interests.
    profile = deepcopy(PROFILE)
    profile["interests"] = {"food": 0.9, "history": 0.4, "architecture": 0.4}
    profile["pace"] = 0.0  # two stops a day

    restaurant = make_place("restaurant")
    restaurant["categories"] = ["restaurant"]
    palace = make_place("palace")
    palace["categories"] = ["palace"]

    result = schedule(
        places=[palace, restaurant],
        profile=profile,
        dates=["2026-10-19"],
        category_map={
            "restaurant": ["food"],
            "palace": ["history", "architecture"],
        },
        destination=DESTINATION,
    )

    assert _ids(result)[0] == "restaurant"


def test_place_matching_no_interest_is_skipped():
    unrelated = make_place("bar")
    unrelated["categories"] = ["bar"]

    result = run([unrelated, make_place("museum")])

    assert _ids(result) == ["museum"]


def test_verified_hours_preferred_over_inferred():
    inferred = deepcopy(HOURS)
    inferred["confidence"] = "inferred"

    result = run([
        make_place("guess", hours=inferred),
        make_place("verified"),
    ])

    assert _ids(result)[0] == "verified"
    assert result["days"][0]["items"][0]["confidence"] == "known"


def test_stray_currency_is_skipped_and_warned():
    dollars = make_place("usd")
    dollars["cost"]["currency"] = "USD"

    result = run([dollars, make_place("eur"), make_place("eur-2")])

    assert "usd" not in _ids(result)
    assert any("not in EUR" in warning for warning in result["warnings"])


def test_city_currency_is_used_when_budget_differs():
    # A budget typed in USD for a city priced in EUR: plan anyway, total in EUR,
    # and say the budget could not be applied instead of returning an empty trip.
    profile = deepcopy(PROFILE)
    profile["budget"] = {"total": 1, "currency": "USD"}

    result = run([make_place("a", cost=50), make_place("b", cost=50)], profile)

    assert len(_ids(result)) == 2
    assert result["totals"]["currency"] == "EUR"
    assert any("budget was not applied" in w for w in result["warnings"])


def test_items_carry_the_place_name():
    result = run([make_place("museum-1")])

    assert result["days"][0]["items"][0]["name"] == "Place museum-1"


def test_travel_matrix_can_be_built_for_the_candidates():
    seen = []

    def legs(candidates):
        seen.extend(place["id"] for place in candidates)
        return {
            ("a", "b"): {"minutes": 7, "mode": "walk"},
            ("b", "a"): {"minutes": 7, "mode": "walk"},
        }

    result = run([make_place("a"), make_place("b")], matrix=legs)

    assert sorted(seen) == ["a", "b"]
    second = result["days"][0]["items"][1]["travel_from_prev"]
    assert second == {"minutes": 7, "mode": "walk"}
