"""Read the entry price of a place from its OSM tags. Never invents a price.

OSM has two tags for this. fee says whether you pay (fee=yes or fee=no). charge says how
much (charge=5 EUR). parse_cost() turns them into the cost object of the Place contract,
{"amount": 5.0, "currency": "EUR", "confidence": "known"}, plus a status word that says
how the price was found:

    charge_parsed       a charge with exactly one amount                  known
    fee_free            fee=no                                            known
    fee_amount_missing  fee=yes but no charge                             unknown
    charge_ambiguous    a charge with several prices, or one we cannot read  unknown
    default_free        no tags, and the category is usually free (a park)  inferred
    no_data             no tags at all                                    unknown

An unknown price is stored as amount 0.0 with confidence unknown. That means not known,
not free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .categories import FREE_BY_DEFAULT

# The currency for a price that does not name its own: the currency of the country. The
# project covers Lisbon, so Portugal and the euro. Any other country gets XXX, the ISO 4217
# code for no currency.
COUNTRY_CURRENCY = {"PT": "EUR"}

_SYMBOLS = {"€": "EUR", "£": "GBP"}

# An amount: 5, 7.50, 2,50 (decimal comma, as written in Portugal), or a number with
# thousands groups such as 1.500 or 15,000.
_AMOUNT = r"(?<![\d.,])(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d{1,2})?)(?!\d)"


@dataclass
class CostResult:
    cost: dict  # {"amount", "currency", "confidence"}, the Place contract shape
    status: str  # how the price was found, see the table at the top of this file


def currency_for_country(country_code: str) -> str:
    """EUR for PT, XXX for any country we have no currency for."""
    return COUNTRY_CURRENCY.get((country_code or "").upper(), "XXX")


def is_currency_code(code: str) -> bool:
    """True for a real ISO 4217 code such as EUR or USD."""
    return code in _ISO_CURRENCIES


def parse_cost(tags: dict, categories: list[str], fallback_currency: str) -> CostResult:
    """Parse the fee and charge tags of one place. See the table at the top of this file."""
    fee = (tags.get("fee") or "").strip().lower()
    charge = (tags.get("charge") or "").strip()

    if fee != "no" and charge:
        prices = _prices_in(charge)
        if len(prices) == 1:
            amount, currency = prices.pop()
            return _result(amount, currency, "known", "charge_parsed")
        # Several prices (adult and child, say) or none we can read: not a fact.
        return _result(0.0, fallback_currency, "unknown", "charge_ambiguous")
    if fee == "no":
        return _result(0.0, fallback_currency, "known", "fee_free")
    if fee == "yes":
        return _result(0.0, fallback_currency, "unknown", "fee_amount_missing")
    if categories and categories[0] in FREE_BY_DEFAULT:
        return _result(0.0, fallback_currency, "inferred", "default_free")
    return _result(0.0, fallback_currency, "unknown", "no_data")


def _result(amount: float, currency: str, confidence: str, status: str) -> CostResult:
    return CostResult({"amount": amount, "currency": currency, "confidence": confidence}, status)


def _prices_in(charge: str) -> set[tuple[float, str]]:
    """Every distinct (amount, currency) pair in a charge text: 5 EUR, €5, 2,50 EUR..."""
    found = set()
    for match in _AMOUNT_FIRST.finditer(charge):
        found.add((_to_number(match.group(1)), _SYMBOLS.get(match.group(2), match.group(2))))
    for match in _CURRENCY_FIRST.finditer(charge):
        found.add((_to_number(match.group(2)), _SYMBOLS.get(match.group(1), match.group(1))))
    return found


def _to_number(text: str) -> float:
    """1.500 and 15,000 are thousands groups. Otherwise a comma is a decimal point."""
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", text):
        return float(re.sub(r"[.,]", "", text))
    return float(text.replace(",", "."))


# Only real currency codes count, so a word such as ENTRY is never read as TRY (lira).
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
# A currency code or symbol that is not part of a longer word.
_CODES = "|".join(sorted(_ISO_CURRENCIES, key=len, reverse=True))
_CURRENCY = r"(?<![A-Z])(" + _CODES + r"|€|£)(?![A-Z])"
_AMOUNT_FIRST = re.compile(_AMOUNT + r"\s*" + _CURRENCY)  # 5 EUR, 5€
_CURRENCY_FIRST = re.compile(_CURRENCY + r"\s*" + _AMOUNT)  # EUR 5, €5
