"""Tests for extract_profile: free text -> contract-valid TravelerProfile."""

from __future__ import annotations

import pytest

from ai.profile import ProfileExtractionError, extract_profile
from ai.tests.fakes import INTERESTS, FakeLLM, reply
from api.contracts import validate


def _interests(**weights: float) -> dict[str, float]:
    return {name: weights.get(name, 0.5) for name in INTERESTS}


def test_valid_reply_becomes_a_valid_profile():
    llm = FakeLLM(
        reply(
            interests=_interests(food=0.9, nightlife=0.1),
            pace=0.2,
            max_walk_minutes=15,
            budget_total=800,
            budget_currency="EUR",
            dietary=["vegetarian"],
        )
    )
    result = extract_profile("Relaxed foodie trip, vegetarian, 800 euros, short walks.", llm)

    assert validate("traveler-profile", result.profile) == []
    assert result.profile["interests"]["food"] == 0.9
    assert result.profile["budget"] == {"total": 800, "currency": "EUR"}
    assert result.profile["dietary"] == ["vegetarian"]
    assert result.attempts == 1
    assert result.defaults_used == ["day_start", "day_end"]


def test_unmentioned_fields_get_the_form_defaults_and_are_listed():
    result = extract_profile("Somewhere nice.", FakeLLM(reply()))

    assert result.profile["pace"] == 0.4
    assert result.profile["max_walk_minutes"] == 20
    assert (result.profile["day_start"], result.profile["day_end"]) == ("09:30", "22:00")
    assert result.profile["budget"] == {"total": 1200, "currency": "EUR"}
    assert result.defaults_used == [
        "pace",
        "max_walk_minutes",
        "day_start",
        "day_end",
        "budget.total",
        "budget.currency",
    ]


def test_only_the_missing_part_of_the_budget_is_defaulted():
    result = extract_profile("About 2000 for the week.", FakeLLM(reply(budget_total=2000)))

    assert result.profile["budget"] == {"total": 2000, "currency": "EUR"}
    assert "budget.currency" in result.defaults_used
    assert "budget.total" not in result.defaults_used


def test_invalid_json_is_retried_with_the_problem_explained():
    llm = FakeLLM("not json at all", reply(pace=0.8))
    result = extract_profile("Packed trip please.", llm)

    assert result.attempts == 2
    assert result.profile["pace"] == 0.8
    retry = llm.calls[1]["messages"]
    assert retry[-2] == {"role": "assistant", "content": "not json at all"}
    assert "not valid JSON" in retry[-1]["content"]


def test_out_of_range_values_are_sent_back_to_the_model():
    llm = FakeLLM(reply(interests=_interests(food=1.5)), reply(interests=_interests(food=1.0)))
    result = extract_profile("I live for food.", llm)

    assert result.attempts == 2
    assert result.profile["interests"]["food"] == 1.0
    assert "1.5" in llm.calls[1]["messages"][-1]["content"]


def test_unknown_or_missing_interest_names_are_problems():
    unknown = {**_interests(), "beaches": 0.9}
    missing = {name: 0.5 for name in INTERESTS[:-1]}
    llm = FakeLLM(reply(interests=unknown), reply(interests=missing), reply())
    result = extract_profile("Beach time.", llm)

    assert result.attempts == 3
    assert "beaches" in llm.calls[1]["messages"][-1]["content"]
    assert "shopping" in llm.calls[2]["messages"][-1]["content"]


def test_avoid_must_use_the_category_vocabulary():
    llm = FakeLLM(reply(avoid=["churches"]), reply(avoid=["church"]))
    result = extract_profile("No churches please.", llm)

    assert result.profile["avoid"] == ["church"]
    assert "churches" in llm.calls[1]["messages"][-1]["content"]


def test_day_must_end_after_it_starts():
    llm = FakeLLM(reply(day_start="18:00", day_end="09:00"), reply(day_start="09:00"))
    result = extract_profile("Night owl.", llm)

    assert result.attempts == 2
    assert "day_end must be later" in llm.calls[1]["messages"][-1]["content"]


def test_a_non_object_reply_is_a_problem():
    llm = FakeLLM("[1, 2, 3]", reply())
    extract_profile("Hi.", llm)

    assert "must be a JSON object" in llm.calls[1]["messages"][-1]["content"]


def test_mechanical_clean_ups_are_applied():
    llm = FakeLLM(
        reply(
            day_start="9:00",
            budget_total=500,
            budget_currency="€",
            max_walk_minutes=15.0,
            dietary=[" Vegan ", "vegan", "Gluten-Free"],
        )
    )
    result = extract_profile("Vegan, gluten free, 500€, up at 9.", llm)

    assert result.profile["day_start"] == "09:00"
    assert result.profile["budget"]["currency"] == "EUR"
    assert result.profile["max_walk_minutes"] == 15
    assert result.profile["dietary"] == ["vegan", "gluten-free"]


def test_gives_up_after_max_attempts():
    llm = FakeLLM("nope", "still nope", "nope again")
    with pytest.raises(ProfileExtractionError) as err:
        extract_profile("Anything.", llm)

    assert err.value.attempts == 3
    assert err.value.errors == ["The reply was not valid JSON."]
    assert len(llm.calls) == 3


def test_the_model_gets_the_vocabulary_and_a_schema():
    llm = FakeLLM(reply())
    extract_profile("Anything.", llm)

    system = llm.calls[0]["messages"][0]["content"]
    assert all(name in system for name in INTERESTS)
    schema = llm.calls[0]["schema"]
    assert schema["properties"]["interests"]["required"] == INTERESTS
    assert "church" in schema["properties"]["avoid"]["items"]["enum"]
