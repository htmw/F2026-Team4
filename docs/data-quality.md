# Data quality: what a traveler actually gets

Generated 2026-11-18 by `python -m ingest.quality`. Each city is loaded the way the app loads it, then a sample two-day trip is planned for the sample traveler (`fixtures/sample.profile.json`). Plan columns describe the stops in that trip; the last columns describe every place in the city.

- **Verified hours / price**: from the place's own OpenStreetMap listing (or Rome's hand-checked sources). **Estimated**: usual hours or a typical price for that kind of place, shown to the traveler as "estimated" and with ≈.
- **Unknown** is what the traveler would see as "unverified" or "Price unknown".

## In the planned trip

| City | Stops | Hours verified | Hours estimated | Hours unknown | Real price or free | Price ≈ estimate | Price unknown | Described | From Wikipedia | Photo |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Hyderabad, India | 9 | 78% | 22% | 0% | 0% | 100% | 0% | 100% | 22% | 0% |
| New York, United States | 11 | 91% | 9% | 0% | 0% | 100% | 0% | 100% | 27% | 0% |
| Tokyo, Japan | 10 | 90% | 10% | 0% | 10% | 90% | 0% | 100% | 0% | 0% |
| Paris, France | 10 | 100% | 0% | 0% | 0% | 100% | 0% | 100% | 80% | 0% |
| Cairo, Egypt | 9 | 78% | 22% | 0% | 0% | 100% | 0% | 100% | 44% | 0% |
| Sydney, Australia | 10 | 80% | 20% | 0% | 20% | 80% | 0% | 100% | 60% | 0% |
| Mexico City, Mexico | 10 | 70% | 30% | 0% | 0% | 100% | 0% | 100% | 40% | 0% |
| Rome, Italy | 11 | 100% | 0% | 0% | 64% | 36% | 0% | 0% | 0% | 0% |
| Greater London, United Kingdom | 10 | 80% | 20% | 0% | 10% | 90% | 0% | 100% | 90% | 0% |
| Berlin, Germany | 11 | 91% | 9% | 0% | 18% | 82% | 0% | 100% | 64% | 0% |
| Istanbul, Turkey | 12 | 83% | 17% | 0% | 0% | 100% | 0% | 100% | 67% | 0% |
| Dubai, United Arab Emirates | 11 | 73% | 27% | 0% | 18% | 82% | 0% | 100% | 36% | 0% |
| Bangkok, Thailand | 9 | 89% | 11% | 0% | 11% | 89% | 0% | 100% | 44% | 0% |
| Seoul, South Korea | 9 | 89% | 11% | 0% | 0% | 100% | 0% | 100% | 67% | 0% |
| Singapore, Singapore | 10 | 80% | 20% | 0% | 0% | 100% | 0% | 100% | 80% | 0% |
| Nairobi, Kenya | 9 | 67% | 33% | 0% | 0% | 100% | 0% | 100% | 67% | 0% |
| Cape Town, South Africa | 10 | 80% | 20% | 0% | 0% | 100% | 0% | 100% | 50% | 0% |
| Lima, Peru | 10 | 90% | 10% | 0% | 10% | 90% | 0% | 100% | 60% | 0% |
| Buenos Aires, Argentina | 9 | 89% | 11% | 0% | 11% | 89% | 0% | 100% | 56% | 0% |
| Toronto, Canada | 11 | 73% | 27% | 0% | 0% | 100% | 0% | 100% | 91% | 0% |

## The city as a whole

| City | Currency | Places | Loaded in | Median walk to a bus stop or station | Places within 5 min of one | Rides in the trip (walk min each) |
|---|---|---:|---:|---:|---:|---|
| Hyderabad, India | INR | 357 | 0.0 s (saved) | 4.7 min | 52% | 5 (2, 4, 9, 10, 14) |
| New York, United States | USD | 6981 | 0.3 s (saved) | 1.2 min | 99% | 6 (2, 2, 2, 2, 2, 2) |
| Tokyo, Japan | JPY | 6437 | 0.3 s (saved) | 1.4 min | 99% | 4 (4, 4, 4, 5) |
| Paris, France | EUR | 15882 | 1.0 s (saved) | 1.3 min | 100% | 6 (2, 2, 2, 3, 3, 3) |
| Cairo, Egypt | EGP | 493 | 0.0 s (saved) | 7.2 min | 29% | 5 (7, 10, 14, 19, 27) |
| Sydney, Australia | AUD | 3911 | 0.4 s (saved) | 1.3 min | 96% | 2 (1, 3) |
| Mexico City, Mexico | MXN | 1058 | 0.0 s (saved) | 4.2 min | 59% | 4 (13, 15, 17, 19) |
| Rome, Italy | EUR | 4549 | 0.1 s (saved) | n/a | n/a | 5 (6, 6, 6, 6, 6) |
| Greater London, United Kingdom | GBP | 9536 | 0.6 s (saved) | 1.3 min | 98% | 5 (1, 2, 3, 3, 4) |
| Berlin, Germany | EUR | 7098 | 0.6 s (saved) | 2.0 min | 96% | 3 (4, 5, 6) |
| Istanbul, Turkey | TRY | 5131 | 0.1 s (saved) | 2.2 min | 92% | 3 (3, 4, 6) |
| Dubai, United Arab Emirates | AED | 1247 | 0.0 s (saved) | 2.8 min | 77% | 4 (3, 3, 4, 6) |
| Bangkok, Thailand | THB | 2420 | 0.1 s (saved) | 1.8 min | 93% | 3 (4, 7, 8) |
| Seoul, South Korea | KRW | 1770 | 0.1 s (saved) | 1.6 min | 98% | 6 (3, 4, 5, 5, 8, 8) |
| Singapore, Singapore | SGD | 3973 | 0.9 s (saved) | 1.5 min | 98% | 3 (6, 7, 9) |
| Nairobi, Kenya | KES | 1469 | 46.6 s (fresh fetch) | 5.9 min | 43% | 6 (9, 11, 13, 14, 16, 17) |
| Cape Town, South Africa | ZAR | 830 | 85.0 s (fresh fetch) | 1.8 min | 88% | 2 (3, 5) |
| Lima, Peru | PEN | 1990 | 54.1 s (fresh fetch) | 3.5 min | 68% | 3 (3, 11, 13) |
| Buenos Aires, Argentina | ARS | 3695 | 104.2 s (fresh fetch) | 1.2 min | 99% | 5 (1, 3, 3, 3, 4) |
| Toronto, Canada | CAD | 3586 | 117.3 s (fresh fetch) | 1.2 min | 98% | 6 (2, 2, 3, 3, 4, 4) |

## Reading it

- Across 20 cities, no planned stop has unknown hours or prices: every stop has a verified value or an estimate the traveler can see is one.
- Saved cities from before descriptions and bus stops existed (Rome's committed snapshot) show 0% described and no walk-to-stop data; live cities fetched now have both.
