"""Tests for parsing OSM fee and charge tags."""

import pytest

from ingest.cost import COUNTRY_CURRENCY, currency_for_country, parse_cost, typical_price


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


def test_fee_yes_without_price_gets_an_estimate():
    result = parse_cost({"fee": "yes"}, [], "USD")

    assert result.cost == {"amount": 20.0, "currency": "USD", "confidence": "inferred"}
    assert result.status == "fee_amount_missing"


def test_ambiguous_price_is_not_marked_known():
    result = parse_cost({"charge": "adult €10, child €5"}, [], "EUR")

    assert result.cost["confidence"] == "unknown"
    assert result.status == "charge_ambiguous"


def test_a_missing_price_gets_a_typical_estimate_never_a_known_one():
    meal = parse_cost({}, ["restaurant"], "INR")
    ticket = parse_cost({"fee": "yes"}, ["museum"], "EUR")

    assert meal.cost == {"amount": 700.0, "currency": "INR", "confidence": "inferred"}
    assert meal.status == "typical_price"
    assert ticket.cost == {"amount": 12.0, "currency": "EUR", "confidence": "inferred"}


def test_a_real_price_or_free_entry_beats_the_estimate():
    assert parse_cost({"charge": "15 EUR"}, ["museum"], "EUR").cost["amount"] == 15.0
    assert parse_cost({"fee": "no"}, ["museum"], "EUR").cost["amount"] == 0.0
    assert parse_cost({}, ["park"], "INR").cost["amount"] == 0.0


def test_every_currency_gets_an_estimate():
    """Nepal has no row of its own: a base price converted at a rough rate, rounded."""
    result = parse_cost({}, ["restaurant"], "NPR")

    assert result.cost == {"amount": 2100.0, "currency": "NPR", "confidence": "inferred"}
    assert result.status == "typical_price"
    currencies = set(COUNTRY_CURRENCY.values())
    missing = sorted(c for c in currencies if typical_price(["museum"], c) is None)
    assert missing == [], "every country's currency has an estimate"


def test_without_any_currency_the_price_stays_unknown():
    result = parse_cost({}, ["restaurant"], "XXX")

    assert result.cost["confidence"] == "unknown"
    assert result.status == "no_data"


def test_an_unreadable_charge_falls_back_to_the_typical_price():
    result = parse_cost({"charge": "15 EUR adults, 8 EUR children"}, ["museum"], "EUR")

    assert result.cost == {"amount": 12.0, "currency": "EUR", "confidence": "inferred"}
    assert result.status == "charge_ambiguous"


def test_a_day_trip_is_priced_like_a_museum():
    assert typical_price(["day_trip"], "EUR") == typical_price(["museum"], "EUR")


def test_country_currency_lookup():
    assert currency_for_country("US") == "USD"
    assert currency_for_country("IN") == "INR"
    assert currency_for_country("pt") == "EUR"
    assert currency_for_country("??") == "XXX"
    assert currency_for_country("GE") == "GEL"
    assert currency_for_country("PK") == "PKR"
    assert currency_for_country("KE") == "KES"
    assert currency_for_country("BG") == "EUR"  # joined the euro in 2026


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


ISO_COUNTRIES = """
AD AE AF AG AI AL AM AO AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT
BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG
EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN
HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI
LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC
NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA
SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR
TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
""".split()  # every ISO 3166 country except Antarctica, which has no currency


def test_every_country_has_a_currency():
    missing = [c for c in ISO_COUNTRIES if currency_for_country(c) == "XXX"]
    assert missing == []
    assert currency_for_country("CO") == "COP"
    assert currency_for_country("JP") == "JPY"


@pytest.mark.parametrize("tags", [
    {"tourism": "attraction", "building": "office", "height": "443"},       # Empire State
    {"tourism": "attraction", "building": "yes", "building:levels": "104"},  # One WTC
    {"tourism": "attraction", "man_made": "tower"},                          # Eiffel Tower
    {"man_made": "tower", "tower:type": "communication;observation"},       # Tokyo Tower
])
def test_a_tower_with_a_viewing_deck_gets_an_estimated_ticket(tags):
    result = parse_cost(tags, ["landmark"], "USD")

    assert result.cost == {"amount": 40.0, "currency": "USD", "confidence": "inferred"}


@pytest.mark.parametrize("tags", [
    {"tourism": "attraction", "amenity": "fountain"},                 # Trevi Fountain
    {"tourism": "attraction", "building": "yes", "height": "30"},     # a low building
    {"historic": "tower", "fee": "no"},                               # tagged as free
])
def test_other_landmarks_stay_free(tags):
    assert parse_cost(tags, ["landmark"], "EUR").cost["amount"] == 0.0


def test_a_paid_park_without_an_amount_gets_a_museum_ticket_estimate():
    result = parse_cost({"fee": "yes"}, ["park"], "EUR")

    assert result.cost == {"amount": 12.0, "currency": "EUR", "confidence": "inferred"}
