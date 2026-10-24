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
