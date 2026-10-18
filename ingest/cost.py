"""Derive the contract `cost` object from OSM fee/charge tags. Never invents prices."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .categories import FREE_BY_DEFAULT

# Fallback currency by ISO country. Only matters when the amount is 0 (a known-free place
# or an unknown price), since a real `charge` carries its own currency. Unlisted -> "XXX"
# (ISO 4217 "no currency"). Extend as needed.
_EURO = "AT BE HR CY EE FI FR DE GR IE IT LV LT LU MT NL PT SK SI ES".split()

COUNTRY_CURRENCY = {
    **{c: "EUR" for c in _EURO},
    "GB": "GBP",
    "US": "USD",
    "CA": "CAD",
    "AU": "AUD",
    "NZ": "NZD",
    "JP": "JPY",
    "CN": "CNY",
    "IN": "INR",
    "BR": "BRL",
    "MX": "MXN",
    "CH": "CHF",
    "SE": "SEK",
    "NO": "NOK",
    "DK": "DKK",
    "PL": "PLN",
    "CZ": "CZK",
    "HU": "HUF",
    "RO": "RON",
    "IS": "ISK",
    "TR": "TRY",
    "RU": "RUB",
    "UA": "UAH",
    "ZA": "ZAR",
    "EG": "EGP",
    "MA": "MAD",
    "AE": "AED",
    "SA": "SAR",
    "IL": "ILS",
    "TH": "THB",
    "VN": "VND",
    "ID": "IDR",
    "MY": "MYR",
    "SG": "SGD",
    "KR": "KRW",
    "HK": "HKD",
    "TW": "TWD",
    "PH": "PHP",
    "AR": "ARS",
    "CL": "CLP",
    "CO": "COP",
    "GE": "GEL",
    "PE": "PEN",
}


_SYMBOLS = {"€": "EUR", "£": "GBP"}

# Recognize only valid currency codes, not arbitrary three-letter words.
# Keep this list aligned with ISO 4217 currency codes used by the parser.
_ISO_CURRENCIES = set(
    """
    AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF
    BMD BND BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC
    CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS
    GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD
    JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL
    LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD
    NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD
    RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SLL SOS SRD SSP STN SVC
    SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS
    VES VND VUV WST XAF XCD XCG XOF XPF YER ZAR ZMW ZWG
    """.split()
)

# Accept ordinary decimal amounts and grouped thousands such as 15,000 or 2.500.
_AMOUNT = r"(?<![\d.,])(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d{1,2})?)(?!\d)"

# Currency codes must not be embedded in longer uppercase words.
_CUR = r"(?<![A-Z])(" + "|".join(sorted(_ISO_CURRENCIES, key=len, reverse=True)) + r"|€|£)(?![A-Z])"

_AMOUNT_FIRST = re.compile(_AMOUNT + r"\s*" + _CUR)
_CUR_FIRST = re.compile(_CUR + r"\s*" + _AMOUNT)


def is_currency_code(code: str) -> bool:
    """True for a real ISO 4217 code such as EUR or GEL."""
    return code in _ISO_CURRENCIES


def currency_for_country(country_code: str) -> str:
    """Return the ISO currency for a country code, or XXX if unknown."""
    return COUNTRY_CURRENCY.get((country_code or "").upper(), "XXX")


@dataclass
class CostResult:
    cost: dict
    # charge_parsed | fee_free | fee_amount_missing | charge_ambiguous | default_free | no_data
    status: str


def _cur(token: str) -> str:
    """Convert a recognized currency symbol to its ISO currency code."""
    return _SYMBOLS.get(token, token)


def _amounts(charge: str) -> set[tuple[float, str]]:
    """Extract distinct amount/currency pairs from a charge string."""
    found: set[tuple[float, str]] = set()

    def parse_amount(token: str) -> float:
        # A number with groups of three digits is interpreted as thousands.
        # For example, 15,000 -> 15000 and 2.500 -> 2500.
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", token):
            return float(re.sub(r"[.,]", "", token))

        # Otherwise, a comma is treated as a decimal separator.
        return float(token.replace(",", "."))

    for match in _AMOUNT_FIRST.finditer(charge):
        found.add((parse_amount(match.group(1)), _cur(match.group(2))))

    for match in _CUR_FIRST.finditer(charge):
        found.add((parse_amount(match.group(2)), _cur(match.group(1))))

    return found


def parse_cost(tags: dict, categories: list[str], fallback_currency: str) -> CostResult:
    """Parse fee and charge tags into the project's cost contract."""
    fee = (tags.get("fee") or "").strip().lower()
    charge = (tags.get("charge") or "").strip()

    def mk(amount: float, currency: str, confidence: str, status: str) -> CostResult:
        return CostResult(
            {
                "amount": amount,
                "currency": currency,
                "confidence": confidence,
            },
            status,
        )

    if fee != "no" and charge:
        found = _amounts(charge)

        if len(found) == 1:
            amount, currency = next(iter(found))
            return mk(amount, currency, "known", "charge_parsed")

        # Multiple prices, price tiers, or unparseable charges are not reliable.
        return mk(0.0, fallback_currency, "unknown", "charge_ambiguous")

    if fee == "no":
        return mk(0.0, fallback_currency, "known", "fee_free")

    if fee == "yes":
        return mk(0.0, fallback_currency, "unknown", "fee_amount_missing")

    if categories and categories[0] in FREE_BY_DEFAULT:
        return mk(0.0, fallback_currency, "inferred", "default_free")
    return mk(0.0, fallback_currency, "unknown", "no_data")
