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
    "PE": "PEN",
}
_SYMBOLS = {"€": "EUR", "£": "GBP"}  # "$" and "¥" are ambiguous, so they are not interpreted

_AMOUNT = r"(\d+(?:[.,]\d{1,2})?)"
_CUR = r"([A-Z]{3}|€|£)"
_AMOUNT_FIRST = re.compile(_AMOUNT + r"\s*" + _CUR)
_CUR_FIRST = re.compile(_CUR + r"\s*" + _AMOUNT)


def currency_for_country(country_code: str) -> str:
    return COUNTRY_CURRENCY.get((country_code or "").upper(), "XXX")


@dataclass
class CostResult:
    cost: dict
    # charge_parsed | fee_free | fee_amount_missing | charge_ambiguous | default_free | no_data
    status: str


def _cur(token: str) -> str:
    return _SYMBOLS.get(token, token)


def _amounts(charge: str) -> set[tuple[float, str]]:
    found = set()
    for m in _AMOUNT_FIRST.finditer(charge):
        found.add((float(m.group(1).replace(",", ".")), _cur(m.group(2))))
    for m in _CUR_FIRST.finditer(charge):
        found.add((float(m.group(2).replace(",", ".")), _cur(m.group(1))))
    return found


def parse_cost(tags: dict, categories: list[str], fallback_currency: str) -> CostResult:
    fee = (tags.get("fee") or "").strip().lower()
    charge = (tags.get("charge") or "").strip()

    def mk(amount: float, currency: str, confidence: str, status: str) -> CostResult:
        return CostResult(
            {"amount": amount, "currency": currency, "confidence": confidence}, status
        )

    if fee != "no" and charge:
        found = _amounts(charge)
        if len(found) == 1:
            amount, currency = next(iter(found))
            return mk(amount, currency, "known", "charge_parsed")
        return mk(0.0, fallback_currency, "unknown", "charge_ambiguous")  # tiers or unparseable
    if fee == "no":
        return mk(0.0, fallback_currency, "known", "fee_free")
    if fee == "yes":
        return mk(0.0, fallback_currency, "unknown", "fee_amount_missing")
    if categories and categories[0] in FREE_BY_DEFAULT:
        return mk(0.0, fallback_currency, "inferred", "default_free")
    return mk(0.0, fallback_currency, "unknown", "no_data")
