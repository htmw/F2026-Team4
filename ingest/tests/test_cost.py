"""Tests for reading the price of a place from the OSM fee and charge tags."""

import pytest

from ingest.cost import currency_for_country, parse_cost


def test_parses_price_with_currency():
    result = parse_cost({"charge": "€12.50"}, [], "EUR")

    assert result.cost == {
        "amount": 12.5,
        "currency": "EUR",
        "confidence": "known",
    }
    assert result.status == "charge_parsed"


@pytest.mark.parametrize(
    "charge, amount",
    [
        ("5 EUR", 5.0),  # the most common form in the Lisbon data
        ("2EUR", 2.0),
        ("7.50 EUR", 7.5),
        ("2,50 EUR", 2.5),  # decimal comma, as written in Portugal
        ("1.500 EUR", 1500.0),  # a thousands group
        ("€5 PER PERSON", 5.0),
    ],
)
def test_reads_the_ways_lisbon_prices_are_written(charge, amount):
    result = parse_cost({"charge": charge, "fee": "yes"}, ["museum"], "EUR")

    assert result.cost == {"amount": amount, "currency": "EUR", "confidence": "known"}
    assert result.status == "charge_parsed"


def test_fee_no_means_known_free():
    result = parse_cost({"fee": "no"}, [], "EUR")

    assert result.cost == {"amount": 0.0, "currency": "EUR", "confidence": "known"}
    assert result.status == "fee_free"


def test_fee_yes_without_price_is_unknown():
    result = parse_cost({"fee": "yes"}, [], "EUR")

    assert result.cost["confidence"] == "unknown"
    assert result.status == "fee_amount_missing"


def test_ambiguous_price_is_not_marked_known():
    result = parse_cost({"charge": "adult €10, child €5"}, [], "EUR")

    assert result.cost["confidence"] == "unknown"
    assert result.status == "charge_ambiguous"


def test_does_not_read_a_currency_code_inside_a_word():
    # ENTRY ends in TRY, the Turkish lira code. It must not become a price in lira.
    result = parse_cost({"charge": "ENTRY 10"}, [], "EUR")

    assert result.cost["confidence"] == "unknown"
    assert result.status == "charge_ambiguous"


def test_no_tags_on_a_usually_free_category_is_inferred_free():
    result = parse_cost({}, ["park"], "EUR")

    assert result.cost == {"amount": 0.0, "currency": "EUR", "confidence": "inferred"}
    assert result.status == "default_free"


def test_missing_price_is_unknown_for_regular_category():
    result = parse_cost({}, ["restaurant"], "EUR")

    assert result.cost["confidence"] == "unknown"
    assert result.status == "no_data"


def test_country_currency_lookup():
    assert currency_for_country("PT") == "EUR"
    assert currency_for_country("pt") == "EUR"
    assert currency_for_country("") == "XXX"
    assert currency_for_country("??") == "XXX"
