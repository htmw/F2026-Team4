"""Tests for parsing OSM fee and charge tags."""

from ingest.cost import currency_for_country, parse_cost


def test_parses_price_with_currency():
    result = parse_cost({"charge": "€12.50"}, [], "EUR")

    assert result.cost == {
        "amount": 12.5,
        "currency": "EUR",
        "confidence": "known",
    }
    assert result.status == "charge_parsed"


def test_fee_no_means_known_free():
    result = parse_cost({"fee": "no"}, [], "USD")

    assert result.cost["amount"] == 0.0
    assert result.cost["currency"] == "USD"
    assert result.cost["confidence"] == "known"
    assert result.status == "fee_free"


def test_fee_yes_without_price_is_unknown():
    result = parse_cost({"fee": "yes"}, [], "USD")

    assert result.cost["confidence"] == "unknown"
    assert result.status == "fee_amount_missing"


def test_ambiguous_price_is_not_marked_known():
    result = parse_cost({"charge": "adult €10, child €5"}, [], "EUR")

    assert result.cost["confidence"] == "unknown"
    assert result.status == "charge_ambiguous"


def test_missing_price_is_unknown_for_regular_category():
    result = parse_cost({}, ["restaurant"], "USD")

    assert result.cost["confidence"] == "unknown"
    assert result.status == "no_data"


def test_country_currency_lookup():
    assert currency_for_country("US") == "USD"
    assert currency_for_country("IN") == "INR"
    assert currency_for_country("pt") == "EUR"
    assert currency_for_country("??") == "XXX"
