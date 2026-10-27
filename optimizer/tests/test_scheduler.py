
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
    # A traveler who loves food should get the cafe before a palace that matches
    # two weaker interests.
    profile = deepcopy(PROFILE)
    profile["interests"] = {"food": 0.9, "history": 0.4, "architecture": 0.4}

    cafe = make_place("cafe")
    cafe["categories"] = ["cafe"]
    palace = make_place("palace")
    palace["categories"] = ["palace"]

    result = schedule(
        places=[palace, cafe],
        profile=profile,
        dates=["2026-10-19"],
        category_map={
            "cafe": ["food"],
            "palace": ["history", "architecture"],
        },
        destination=DESTINATION,
    )

    assert _ids(result)[0] == "cafe"


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


# ---- interests, time of day, day length -----------------------------------------------

ALL_DAY = {day: [["08:00", "23:30"]] for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
ALL_DAY["confidence"] = "known"

LONG_DAY = {
    **PROFILE,
    "day_start": "09:00",
    "day_end": "22:30",
    "daily_active_hours": 9,
    "budget": {"total": 1000, "currency": "EUR"},
}

MAP = {
    "museum": ["history", "art"],
    "church": ["history", "architecture"],
    "gallery": ["art"],
    "restaurant": ["food"],
    "cafe": ["food"],
    "bar": ["nightlife"],
    "park": ["nature"],
}


def place_of(place_id, category, duration=60):
    place = make_place(place_id, cost=0, duration=duration, hours=ALL_DAY)
    place["categories"] = [category]
    return place


def plan(places, interests, **overrides):
    profile = deepcopy(LONG_DAY)
    profile["interests"] = interests
    profile.update(overrides)
    return schedule(
        places=places,
        profile=profile,
        dates=["2026-10-19"],
        category_map=MAP,
        destination=DESTINATION,
    )


def _items(result):
    return [item for day in result["days"] for item in day["items"]]


def test_reason_lists_every_matched_interest():
    result = plan([place_of("church", "church")], {"history": 0.8, "architecture": 0.7})

    reason = _items(result)[0]["reason"]
    assert "history" in reason and "architecture" in reason


def test_bars_only_in_the_evening():
    places = [place_of("bar", "bar")] + [place_of(f"park-{i}", "park") for i in range(3)]

    result = plan(places, {"nightlife": 1.0, "nature": 0.5})

    bar = next(i for i in _items(result) if i["place_id"] == "bar")
    assert bar["start"] >= "18:00"


def test_lunch_and_dinner_at_meal_times():
    places = [place_of(f"r{i}", "restaurant", 75) for i in range(4)]
    places += [place_of(f"m{i}", "museum", 90) for i in range(6)]

    result = plan(places, {"food": 0.8, "history": 0.8, "art": 0.5})

    meals = [i for i in _items(result) if i["place_id"].startswith("r")]
    assert len(meals) == 2
    lunch, dinner = sorted(meal["start"] for meal in meals)
    assert "12:00" <= lunch <= "14:30"
    assert "19:00" <= dinner <= "21:30"


def test_day_is_filled_by_time_not_a_fixed_stop_count():
    places = [place_of(f"p{i}", "park", 45) for i in range(12)]

    result = plan(places, {"nature": 1.0}, pace=1.0)

    # The old rule capped a packed day at 6 stops; 9 active hours fit more.
    assert len(_items(result)) > 6


def test_relaxed_pace_gets_more_breathing_room():
    places = [place_of(f"p{i}", "park", 45) for i in range(12)]

    packed = plan(places, {"nature": 1.0}, pace=1.0)
    relaxed = plan(places, {"nature": 1.0}, pace=0.0)

    assert len(_items(relaxed)) < len(_items(packed))


def test_interest_mix_follows_the_weights():
    # Art weighs twice as much as nature: art gets more stops, but nature still gets some.
    places = [place_of(f"g{i}", "gallery", 45) for i in range(10)]
    places += [place_of(f"p{i}", "park", 45) for i in range(10)]

    result = plan(places, {"art": 1.0, "nature": 0.5}, pace=1.0)

    ids = [i["place_id"] for i in _items(result)]
    art = sum(pid.startswith("g") for pid in ids)
    nature = sum(pid.startswith("p") for pid in ids)
    assert nature >= 1
    assert art > nature
