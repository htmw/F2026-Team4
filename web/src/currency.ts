// Pick the budget currency from the destination's country, so the optimizer can apply the
// budget (it only does when the budget is in the same currency as the local prices).
// This table is a copy of _COUNTRY_CURRENCY_TABLE in ingest/cost.py, which the backend uses
// to price places. Keep the two in sync.
const COUNTRY_CURRENCY_TABLE = `
  AD:EUR AE:AED AF:AFN AG:XCD AI:XCD AL:ALL AM:AMD AO:AOA AR:ARS AS:USD AT:EUR AU:AUD
  AW:AWG AX:EUR AZ:AZN BA:BAM BB:BBD BD:BDT BE:EUR BF:XOF BG:EUR BH:BHD BI:BIF BJ:XOF
  BL:EUR BM:BMD BN:BND BO:BOB BQ:USD BR:BRL BS:BSD BT:BTN BV:NOK BW:BWP BY:BYN BZ:BZD
  CA:CAD CC:AUD CD:CDF CF:XAF CG:XAF CH:CHF CI:XOF CK:NZD CL:CLP CM:XAF CN:CNY CO:COP
  CR:CRC CU:CUP CV:CVE CW:XCG CX:AUD CY:EUR CZ:CZK DE:EUR DJ:DJF DK:DKK DM:XCD DO:DOP
  DZ:DZD EC:USD EE:EUR EG:EGP EH:MAD ER:ERN ES:EUR ET:ETB FI:EUR FJ:FJD FK:FKP FM:USD
  FO:DKK FR:EUR GA:XAF GB:GBP GD:XCD GE:GEL GF:EUR GG:GBP GH:GHS GI:GIP GL:DKK GM:GMD
  GN:GNF GP:EUR GQ:XAF GR:EUR GS:GBP GT:GTQ GU:USD GW:XOF GY:GYD HK:HKD HM:AUD HN:HNL
  HR:EUR HT:HTG HU:HUF ID:IDR IE:EUR IL:ILS IM:GBP IN:INR IO:USD IQ:IQD IR:IRR IS:ISK
  IT:EUR JE:GBP JM:JMD JO:JOD JP:JPY KE:KES KG:KGS KH:KHR KI:AUD KM:KMF KN:XCD KP:KPW
  KR:KRW KW:KWD KY:KYD KZ:KZT LA:LAK LB:LBP LC:XCD LI:CHF LK:LKR LR:LRD LS:LSL LT:EUR
  LU:EUR LV:EUR LY:LYD MA:MAD MC:EUR MD:MDL ME:EUR MF:EUR MG:MGA MH:USD MK:MKD ML:XOF
  MM:MMK MN:MNT MO:MOP MP:USD MQ:EUR MR:MRU MS:XCD MT:EUR MU:MUR MV:MVR MW:MWK MX:MXN
  MY:MYR MZ:MZN NA:NAD NC:XPF NE:XOF NF:AUD NG:NGN NI:NIO NL:EUR NO:NOK NP:NPR NR:AUD
  NU:NZD NZ:NZD OM:OMR PA:PAB PE:PEN PF:XPF PG:PGK PH:PHP PK:PKR PL:PLN PM:EUR PN:NZD
  PR:USD PS:ILS PT:EUR PW:USD PY:PYG QA:QAR RE:EUR RO:RON RS:RSD RU:RUB RW:RWF SA:SAR
  SB:SBD SC:SCR SD:SDG SE:SEK SG:SGD SH:SHP SI:EUR SJ:NOK SK:EUR SL:SLE SM:EUR SN:XOF
  SO:SOS SR:SRD SS:SSP ST:STN SV:USD SX:XCG SY:SYP SZ:SZL TC:USD TD:XAF TF:EUR TG:XOF
  TH:THB TJ:TJS TK:NZD TL:USD TM:TMT TN:TND TO:TOP TR:TRY TT:TTD TV:AUD TW:TWD TZ:TZS
  UA:UAH UG:UGX UM:USD US:USD UY:UYU UZ:UZS VA:EUR VC:XCD VE:VES VG:USD VI:USD VN:VND
  VU:VUV WF:XPF WS:WST XK:EUR YE:YER YT:EUR ZA:ZAR ZM:ZMW ZW:ZWG
`;

const COUNTRY_CURRENCY: Record<string, string> = Object.fromEntries(
  COUNTRY_CURRENCY_TABLE.trim()
    .split(/\s+/)
    .map((pair) => pair.split(":") as [string, string]),
);

/** ISO 4217 currency for an ISO 3166 alpha-2 country code, or undefined if unknown. */
export function currencyForCountry(countryCode: string | undefined): string | undefined {
  if (!countryCode) return undefined;
  return COUNTRY_CURRENCY[countryCode.toUpperCase()];
}

/** Offered in the budget currency dropdown; the destination's own currency is added if missing. */
export const COMMON_CURRENCIES = [
  "EUR", "USD", "GBP", "INR", "JPY", "CNY", "AUD", "CAD", "CHF", "SGD", "AED", "THB",
];

/** The dropdown options: the common list, plus `current` if it is not already in it. */
export function currencyOptions(current: string): string[] {
  return COMMON_CURRENCIES.includes(current) ? COMMON_CURRENCIES : [current, ...COMMON_CURRENCIES];
}

/** "JPY – Japanese Yen", falling back to the bare code where Intl has no name for it. */
export function currencyLabel(code: string, locale?: string): string {
  try {
    const name = new Intl.DisplayNames(locale, { type: "currency" }).of(code);
    return name && name !== code ? `${code} – ${name}` : code;
  } catch {
    return code;
  }
}
