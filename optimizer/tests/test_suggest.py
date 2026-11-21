"""Tests for swap/add suggestions (optimizer.suggest)."""

from copy import deepcopy

from optimizer.suggest import MAX_SUGGESTIONS, suggest
from optimizer.tests.test_scheduler import DESTINATION, PROFILE, make_place

MAP = {"museum": ["history", "art"], "gallery": ["art"], "park": ["nature"]}


def place(place_id, category="museum", lat=38.72, lon=-9.14, rating=4.5, hours=None):
    p = make_place(place_id, hours=hours)
    p["categories"] = [category]
    p["lat"], p["lon"], p["rating"] = lat, lon, rating
    return p


def trip(*days):
    """A minimal itinerary: each day is (date, [place_id, ...])."""
    return {
        "destination": DESTINATION,
        "totals": {"cost": 0, "currency": "EUR", "walking_minutes": 0},
        "days": [
            {"date": d, "items": [{"place_id": pid} for pid in ids]} for d, ids in days
        ],
    }


def profile(**changes):
    p = deepcopy(PROFILE)
    p["interests"] = {"history": 1.0, "art": 0.6}
    p.update(changes)
    return p


def ids(found):
    return [s["place_id"] for s in found]


def test_at_most_five_and_never_a_place_already_in_the_trip():
    places = [place(f"m{i}") for i in range(9)]

    found = suggest(places, profile(), trip(("2026-10-19", ["m0", "m1"])), MAP)

    assert len(found) == MAX_SUGGESTIONS
    assert not {"m0", "m1"} & set(ids(found))


def test_rejected_avoided_and_off_interest_places_are_left_out():
    places = [place("kept"), place("rejected"), place("avoided"), place("park", "park")]
    p = profile(avoid=["avoided"], feedback={"accepted": [], "rejected": ["rejected"]})

    found = suggest(places, p, trip(("2026-10-19", [])), MAP)

    assert ids(found) == ["kept"]


def test_each_suggestion_has_what_the_website_reads():
    found = suggest([place("m1")], profile(), trip(("2026-10-19", [])), MAP)

    assert found == [{
        "place_id": "m1",
        "name": "Place m1",
        "reason": "Matches your interests in history and art.",
        "cost": 10.0,
        "cost_confidence": "known",
    }]


def test_the_trained_ranker_orders_suggestions_like_planning():
    places = [place("a"), place("b"), place("c")]

    found = suggest(
        places, profile(), trip(("2026-10-19", [])), MAP,
        scorer=lambda p, _profile: {"a": 0.1, "b": 0.9, "c": 0.5}[p["id"]],
    )

    assert ids(found) == ["b", "c", "a"]


def test_a_swap_prefers_places_near_the_stop_it_replaces():
    here = place("old", lat=38.72, lon=-9.14)
    near = place("near", lat=38.721, lon=-9.141)
    far = place("far", lat=38.80, lon=-9.30, rating=5.0)  # ~16 km away, slightly better

    found = suggest([here, near, far], profile(), trip(("2026-10-19", ["old"])), MAP,
                    replace="old")

    assert ids(found)[0] == "near"
    assert "old" not in ids(found)


def test_places_closed_that_day_go_last():
    open_days = ("tue", "wed", "thu", "fri", "sat", "sun")
    monday_closed = {day: [["09:00", "18:00"]] for day in open_days}
    monday_closed["confidence"] = "known"
    closed = place("closed", rating=5.0, hours=monday_closed)

    # 2026-10-19 is a Monday.
    found = suggest([closed, place("open")], profile(), trip(("2026-10-19", [])), MAP,
                    day="2026-10-19")

    assert ids(found) == ["open", "closed"]


def test_rain_that_day_prefers_indoor_places():
    rainy = trip(("2026-10-19", []))
    rainy["days"][0]["weather"] = {"rainy": True, "summary": "Rain"}
    park = place("park", "park", rating=5.0)
    museum = place("museum")
    p = profile(interests={"nature": 1.0, "history": 1.0})

    found = suggest([park, museum], p, rainy, {**MAP, "park": ["nature"]}, day="2026-10-19")

    assert ids(found) == ["museum", "park"]
