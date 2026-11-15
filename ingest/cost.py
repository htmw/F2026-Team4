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


# Every other currency: a base price in US dollars times a rough exchange rate (units per
# USD, late 2025), so no place in any country is left as "Price unknown". The base is about
# half the USD row above, for a mid-cost country; the expensive ones use the full USD row.
# Rough on purpose: shown with ≈, never as a real price.
BASE_USD = (15, 4, 3, 5, 12, 8, 6, 8, 8)
HIGH_COST = {"NOK", "DKK", "SEK", "ISK", "HKD", "NZD", "ILS", "KWD", "QAR", "BHD", "BMD",
             "KYD", "BSD"}
_RATE_TABLE = """
AFN:70 ALL:92 AMD:390 AOA:910 ARS:1400 AWG:1.79 AZN:1.7 BAM:1.68 BBD:2 BDT:122 BHD:0.376
BIF:2950 BMD:1 BND:1.3 BOB:6.9 BSD:1 BTN:88 BWP:13.5 BYN:3 BZD:2 CDF:2850 CLP:950 CRC:505
CUP:24 CVE:95 CZK:21 DJF:178 DKK:6.4 DOP:63 DZD:130 ERN:15 ETB:145 FJD:2.25 FKP:0.75 GEL:2.7
GHS:11 GIP:0.75 GMD:72 GNF:8700 GTQ:7.7 GYD:209 HKD:7.8 HNL:26 HTG:131 HUF:335 IDR:16500
ILS:3.3 IQD:1310 IRR:1000000 ISK:122 JOD:0.709 KGS:87 KHR:4000 KMF:420 KPW:900 KWD:0.306
KYD:0.83 KZT:520 LAK:21700 LBP:89500 LKR:300 LRD:180 LSL:17.5 LYD:5.4 MAD:9.1 MDL:17
MGA:4450 MKD:53 MMK:2100 MNT:3580 MOP:8 MRU:40 MUR:45 MVR:15.4 MWK:1735 MYR:4.2 MZN:64
NAD:17.5 NGN:1500 NIO:36.8 NOK:10.1 NPR:140 NZD:1.72 OMR:0.385 PAB:1 PEN:3.45 PGK:4.2
PHP:58 PKR:282 PLN:3.65 PYG:7100 QAR:3.64 RON:4.4 RSD:101 RUB:80 RWF:1450 SAR:3.75 SBD:8.2
SCR:14.5 SDG:600 SEK:9.5 SHP:0.75 SLE:23 SOS:571 SRD:38 SSP:4500 STN:21 SYP:13000 SZL:17.5
TJS:9.4 TMT:3.5 TND:2.95 TOP:2.4 TTD:6.8 TWD:30.5 TZS:2450 UAH:41.5 UGX:3500 UYU:40
UZS:12000 VES:200 VND:26300 VUV:120 WST:2.75 XAF:560 XCD:2.7 XCG:1.79 XOF:560 XPF:102
YER:240 ZMW:23 ZWG:26.5
"""
USD_RATE = {
    code: float(rate) for code, rate in (item.split(":") for item in _RATE_TABLE.split())
}
# A day trip is priced like a museum ticket.
_PRICED_AS = {"day_trip": "museum"}


def _round_price(value: float) -> float:
    """Two significant figures, so a converted price reads like a real one (2,500 not 2,463)."""
    if value <= 0:
        return 0.0
    digits = len(str(int(value))) - 2
    return float(round(value, -digits)) if digits > 0 else float(round(value))


def typical_price(categories: list[str], currency: str) -> float | None:
    """A rough per-person price for a priced kind of place, or None when there is none."""
    if not categories:
        return None
    kind = _PRICED_AS.get(categories[0], categories[0])
    if kind not in PRICED:
        return None
    column = PRICED.index(kind)
    if currency in TYPICAL_PRICE:
        return float(TYPICAL_PRICE[currency][column])
    if currency in USD_RATE:
        base = TYPICAL_PRICE["USD"] if currency in HIGH_COST else BASE_USD
        return _round_price(base[column] * USD_RATE[currency])
    return None


# Landmarks are free by default (a square, a fountain, a temple), but a tower or skyscraper
# that tourists visit is almost always a paid viewing deck: Empire State Building, One World
# Trade Center, Eiffel Tower, Tokyo Tower. Its estimate is twice a museum ticket ($40 in New
# York, EUR 24 in Paris, about 2,000 yen in Tokyo).
DECK_PRICE_FACTOR = 2
TALL_BUILDING_M = 150
TALL_BUILDING_LEVELS = 40


def _number(text) -> float:
    """The leading number of an OSM value such as "443", "443 m" or "102"; 0 if none."""
    match = re.match(r"\s*(\d+(?:\.\d+)?)", str(text or ""))
    return float(match.group(1)) if match else 0.0


def is_paid_view(tags: dict) -> bool:
    """A tower or tall building visited for its view, which usually charges for the deck."""
    if "observation" in (tags.get("tower:type") or ""):
        return True
    if tags.get("tourism") != "attraction":
        return False
    if tags.get("man_made") == "tower":
        return True
    return (
        _number(tags.get("height")) >= TALL_BUILDING_M
        or _number(tags.get("building:levels")) >= TALL_BUILDING_LEVELS
    )


def deck_price(currency: str) -> float | None:
    museum = typical_price(["museum"], currency)
    return None if museum is None else museum * DECK_PRICE_FACTOR


def estimated_cost(categories: list[str], currency: str) -> dict:
    """The cost to show when nobody knows the real price: free for a usually free kind of
    place, otherwise a typical price. Always an estimate ("inferred"), never "unknown",
    except in the one case with no currency at all (XXX)."""
    if categories and categories[0] in FREE_BY_DEFAULT:
        return {"amount": 0.0, "currency": currency, "confidence": "inferred"}
    typical = typical_price(categories, currency)
    if typical is None:
        return {"amount": 0.0, "currency": currency, "confidence": "unknown"}
    return {"amount": typical, "currency": currency, "confidence": "inferred"}


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

        # Multiple prices, price tiers, or unparseable charges are not reliable: use the
        # typical price for that kind of place instead, marked as an estimate.
        typical = typical_price(categories, fallback_currency)
        if typical is not None:
            return mk(typical, fallback_currency, "inferred", "charge_ambiguous")
        return mk(0.0, fallback_currency, "unknown", "charge_ambiguous")

    if fee == "no":
        return mk(0.0, fallback_currency, "known", "fee_free")

    typical = typical_price(categories, fallback_currency)
    if fee == "yes":
        # Paid, amount unknown: the typical price for this kind of place, or for a park,
        # church or landmark that charges, a museum ticket (a deck price for a tower).
        if is_paid_view(tags):
            typical = deck_price(fallback_currency)
        elif typical is None:
            typical = typical_price(["museum"], fallback_currency)
        if typical is not None:
            return mk(typical, fallback_currency, "inferred", "fee_amount_missing")
        return mk(0.0, fallback_currency, "unknown", "fee_amount_missing")

    if categories and categories[0] in {"landmark", "viewpoint"} and is_paid_view(tags):
        deck = deck_price(fallback_currency)
        if deck is not None:
            return mk(deck, fallback_currency, "inferred", "typical_price")
    if categories and categories[0] in FREE_BY_DEFAULT:
        return mk(0.0, fallback_currency, "inferred", "default_free")
    if typical is not None:
        return mk(typical, fallback_currency, "inferred", "typical_price")
    return mk(0.0, fallback_currency, "unknown", "no_data")
