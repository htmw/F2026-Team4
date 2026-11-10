"""Derive the contract `cost` object from OSM fee/charge tags. Never invents prices."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .categories import FREE_BY_DEFAULT

# Currency for every ISO country and territory (Antarctica has none), so a live fetch
# anywhere prices in local money. Only matters when the amount is 0 (a known-free place or
# an unknown price), since a real `charge` carries its own currency. Unknown code -> "XXX"
# (ISO 4217 "no currency").
_COUNTRY_CURRENCY_TABLE = """
AD:EUR AE:AED AF:AFN AG:XCD AI:XCD AL:ALL AM:AMD AO:AOA AR:ARS AS:USD AT:EUR AU:AUD AW:AWG
AX:EUR AZ:AZN BA:BAM BB:BBD BD:BDT BE:EUR BF:XOF BG:EUR BH:BHD BI:BIF BJ:XOF BL:EUR BM:BMD
BN:BND BO:BOB BQ:USD BR:BRL BS:BSD BT:BTN BV:NOK BW:BWP BY:BYN BZ:BZD CA:CAD CC:AUD CD:CDF
CF:XAF CG:XAF CH:CHF CI:XOF CK:NZD CL:CLP CM:XAF CN:CNY CO:COP CR:CRC CU:CUP CV:CVE CW:XCG
CX:AUD CY:EUR CZ:CZK DE:EUR DJ:DJF DK:DKK DM:XCD DO:DOP DZ:DZD EC:USD EE:EUR EG:EGP EH:MAD
ER:ERN ES:EUR ET:ETB FI:EUR FJ:FJD FK:FKP FM:USD FO:DKK FR:EUR GA:XAF GB:GBP GD:XCD GE:GEL
GF:EUR GG:GBP GH:GHS GI:GIP GL:DKK GM:GMD GN:GNF GP:EUR GQ:XAF GR:EUR GS:GBP GT:GTQ GU:USD
GW:XOF GY:GYD HK:HKD HM:AUD HN:HNL HR:EUR HT:HTG HU:HUF ID:IDR IE:EUR IL:ILS IM:GBP IN:INR
IO:USD IQ:IQD IR:IRR IS:ISK IT:EUR JE:GBP JM:JMD JO:JOD JP:JPY KE:KES KG:KGS KH:KHR KI:AUD
KM:KMF KN:XCD KP:KPW KR:KRW KW:KWD KY:KYD KZ:KZT LA:LAK LB:LBP LC:XCD LI:CHF LK:LKR LR:LRD
LS:LSL LT:EUR LU:EUR LV:EUR LY:LYD MA:MAD MC:EUR MD:MDL ME:EUR MF:EUR MG:MGA MH:USD MK:MKD
ML:XOF MM:MMK MN:MNT MO:MOP MP:USD MQ:EUR MR:MRU MS:XCD MT:EUR MU:MUR MV:MVR MW:MWK MX:MXN
MY:MYR MZ:MZN NA:NAD NC:XPF NE:XOF NF:AUD NG:NGN NI:NIO NL:EUR NO:NOK NP:NPR NR:AUD NU:NZD
NZ:NZD OM:OMR PA:PAB PE:PEN PF:XPF PG:PGK PH:PHP PK:PKR PL:PLN PM:EUR PN:NZD PR:USD PS:ILS
PT:EUR PW:USD PY:PYG QA:QAR RE:EUR RO:RON RS:RSD RU:RUB RW:RWF SA:SAR SB:SBD SC:SCR SD:SDG
SE:SEK SG:SGD SH:SHP SI:EUR SJ:NOK SK:EUR SL:SLE SM:EUR SN:XOF SO:SOS SR:SRD SS:SSP ST:STN
SV:USD SX:XCG SY:SYP SZ:SZL TC:USD TD:XAF TF:EUR TG:XOF TH:THB TJ:TJS TK:NZD TL:USD TM:TMT
TN:TND TO:TOP TR:TRY TT:TTD TV:AUD TW:TWD TZ:TZS UA:UAH UG:UGX UM:USD US:USD UY:UYU UZ:UZS
VA:EUR VC:XCD VE:VES VG:USD VI:USD VN:VND VU:VUV WF:XPF WS:WST XK:EUR YE:YER YT:EUR ZA:ZAR
ZM:ZMW ZW:ZWG
"""
COUNTRY_CURRENCY = dict(pair.split(":") for pair in _COUNTRY_CURRENCY_TABLE.split())


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


# Typical price per person when OSM has none (it almost never does: 0.1 to 1.2% of places in
# the data spike). Rough October 2026 figures for a mid-range meal, coffee, drink or ticket,
# applied as `inferred`, never `known`, and named as estimates in the itinerary. A currency
# missing here keeps the price unknown. Worth a sanity check by someone who lives there.
PRICED = (
    "restaurant", "cafe", "bakery", "bar", "nightclub", "museum", "gallery", "palace", "castle"
)
TYPICAL_PRICE = {
    #      restaurant  cafe  bakery   bar  nightclub museum gallery palace castle
    "EUR": (25, 8, 5, 10, 20, 12, 10, 15, 12),
    "GBP": (25, 7, 5, 10, 20, 10, 10, 20, 15),
    "USD": (30, 10, 6, 12, 25, 20, 15, 20, 15),
    "CAD": (30, 10, 6, 12, 25, 18, 15, 20, 15),
    "AUD": (35, 12, 8, 15, 30, 20, 15, 25, 20),
    "CHF": (40, 12, 8, 15, 30, 15, 12, 20, 15),
    "JPY": (2000, 800, 500, 1000, 3000, 1000, 800, 1000, 800),
    "KRW": (15000, 6000, 4000, 10000, 30000, 5000, 3000, 3000, 3000),
    "CNY": (80, 30, 20, 50, 150, 50, 40, 60, 50),
    "SGD": (25, 8, 5, 15, 30, 20, 15, 20, 15),
    "THB": (300, 100, 60, 200, 500, 200, 150, 500, 200),
    "INR": (700, 300, 150, 600, 1500, 250, 100, 250, 250),
    "AED": (80, 25, 15, 50, 150, 50, 40, 60, 50),
    "TRY": (500, 150, 80, 300, 600, 400, 300, 500, 400),
    "EGP": (400, 100, 50, 300, 600, 300, 200, 500, 300),
    "KES": (1500, 500, 300, 800, 1500, 1200, 1000, 1500, 1000),
    "ZAR": (250, 60, 40, 100, 200, 100, 80, 100, 80),
    "MXN": (300, 80, 40, 150, 400, 90, 70, 100, 80),
    "COP": (40000, 10000, 5000, 20000, 50000, 20000, 15000, 20000, 15000),
    "BRL": (80, 25, 15, 40, 80, 30, 20, 30, 25),
    "JMD": (3000, 1000, 500, 1500, 3000, 1500, 1000, 1500, 1000),
}


def typical_price(categories: list[str], currency: str) -> float | None:
    if not categories or categories[0] not in PRICED or currency not in TYPICAL_PRICE:
        return None
    return float(TYPICAL_PRICE[currency][PRICED.index(categories[0])])


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

    typical = typical_price(categories, fallback_currency)
    if fee == "yes":
        if typical is not None:
            return mk(typical, fallback_currency, "inferred", "typical_price")
        return mk(0.0, fallback_currency, "unknown", "fee_amount_missing")

    if categories and categories[0] in FREE_BY_DEFAULT:
        return mk(0.0, fallback_currency, "inferred", "default_free")
    if typical is not None:
        return mk(typical, fallback_currency, "inferred", "typical_price")
    return mk(0.0, fallback_currency, "unknown", "no_data")
