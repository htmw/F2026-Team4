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
    assert currency_for_country("GE") == "GEL"


def test_parses_thousands_separators():
    cases = [
        ("15,000 VND", 15000.0, "VND"),
        ("2.500 COP", 2500.0, "COP"),
        ("1.200 HUF", 1200.0, "HUF"),
    ]

    for charge, expected_amount, expected_currency in cases:
        result = parse_cost({"charge": charge}, [], "XXX")

        assert result.cost["amount"] == expected_amount
        assert result.cost["currency"] == expected_currency
        assert result.cost["confidence"] == "known"
        assert result.status == "charge_parsed"


def test_does_not_match_currency_code_inside_word():
    result = parse_cost({"charge": "ENTRY 10"}, [], "TRY")

    assert result.cost["confidence"] == "unknown"
    assert result.status == "charge_ambiguous"


def test_euro_price_with_per_person_text():
    result = parse_cost({"charge": "€5 PER PERSON"}, [], "EUR")

    assert result.cost["amount"] == 5.0
    assert result.cost["currency"] == "EUR"
    assert result.cost["confidence"] == "known"
    assert result.status == "charge_parsed"
