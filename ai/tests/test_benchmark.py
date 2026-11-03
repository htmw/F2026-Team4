"""Tests for the LLM spike: expectation checks, the run loop, the summary and the report."""

from __future__ import annotations

import itertools
import json

import pytest

from ai.benchmark import DESCRIPTIONS, check_expectations, render, run, summarize
from ai.llm import LLMError, LLMUnavailable
from ai.tests.fakes import INTERESTS, FakeLLM, reply


def _profile(**overrides):
    profile = {
        "interests": {name: 0.5 for name in INTERESTS},
        "pace": 0.4,
        "max_walk_minutes": 20,
        "day_start": "09:30",
        "day_end": "22:00",
        "budget": {"total": 1200, "currency": "EUR"},
        "dietary": [],
        "accessibility": [],
        "avoid": [],
    }
    profile.update(overrides)
    return profile


def test_checks_pass_and_fail_as_described():
    profile = _profile(
        interests={**_profile()["interests"], "food": 0.9, "nightlife": 0.1},
        pace=0.2,
        dietary=["gluten-free"],
        budget={"total": 148000, "currency": "JPY"},
        day_start="10:30",
    )
    expect = {
        "high": ["food", "art"],
        "low": ["nightlife"],
        "pace": "relaxed",
        "dietary": ["gluten"],
        "budget_total": 150000,
        "currency": "JPY",
        "day_start_at_or_after": "10:00",
        "max_walk_at_most": 10,
    }
    results = dict(check_expectations(profile, expect))

    assert results["food high"] and not results["art high"]
    assert results["nightlife low"] and results["pace relaxed"]
    assert results["dietary gluten"]
    assert results["budget 150000"]  # within 5%
    assert results["currency JPY"] and results["start >= 10:00"]
    assert not results["walk <= 10"]


def test_a_diet_nobody_stated_fails_the_check():
    results = dict(check_expectations(_profile(dietary=["vegetarian"]), {"high": ["food"]}))
    assert results["no invented diet"] is False


def test_run_records_validity_attempts_time_and_checks():
    llm = FakeLLM("garbage", reply(pace=0.8), "x", "x", "x")
    items = [
        {"id": "packed", "text": "Pack it in.", "expect": {"pace": "packed"}},
        {"id": "broken", "text": "Anything.", "expect": {"pace": "packed"}},
    ]
    ticks = itertools.count(step=1.5)
    results = run(llm, items, clock=lambda: next(ticks))

    assert results[0]["valid"] and results[0]["attempts"] == 2
    assert results[0]["checks_passed"] == results[0]["checks_total"] == 2  # pace + no diet
    assert results[0]["seconds"] == 1.5
    assert not results[1]["valid"] and results[1]["checks_total"] == 0
    assert "not valid JSON" in results[1]["error"]


def test_a_failed_call_counts_as_invalid():
    class FlakyLLM:
        def chat(self, messages, schema=None):
            raise LLMError("timed out")

    results = run(FlakyLLM(), [{"id": "a", "text": "Hi."}])
    assert not results[0]["valid"] and results[0]["error"] == "timed out"


def test_an_unreachable_model_stops_the_run():
    class DownLLM:
        def chat(self, messages, schema=None):
            raise LLMUnavailable("down")

    with pytest.raises(LLMUnavailable):
        run(DownLLM(), [{"id": "a", "text": "Hi."}])


def test_summary_and_report():
    llm = FakeLLM(reply(pace=0.8), "x", "x", "x")
    items = [
        {"id": "ok", "text": "Packed.", "expect": {"pace": "packed"}},
        {"id": "bad", "text": "Hi.", "expect": {}},
    ]
    results = run(llm, items)
    summary = summarize(results)

    assert summary["valid"] == 1 and summary["valid_rate"] == 0.5
    assert summary["valid_first_try"] == 1 and summary["fully_correct"] == 1
    report = render(summary, results, "llama3", "Darwin arm64", "2026-11-02")
    assert "| llama3 | 50% (1/2) |" in report
    assert "| ok | yes | 1 |" in report and "| bad | no | 3 |" in report


def test_the_committed_descriptions_are_well_formed():
    items = json.loads(DESCRIPTIONS.read_text(encoding="utf-8"))["descriptions"]
    assert len(items) == 20
    assert len({item["id"] for item in items}) == 20
    for item in items:
        assert item["text"].strip() and item["expect"]
        # Every expectation runs against a default profile without raising.
        check_expectations(_profile(), item["expect"])
