"""Daily weather for a trip and which places are outdoors, for the what-if-it-rains flow.

Forecasts come from Open-Meteo (free, no API key, about 16 days ahead). A date further out
than that gets None, meaning no forecast yet, never a guess. Responses are cached on disk
for a few hours, because forecasts change and the demo should not depend on the network
twice for the same question.

The planner decides what to do with a rainy day. This module only answers two questions:
is this date likely to be wet, and is this place outdoors.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import requests

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
DAILY_FIELDS = (
    "weather_code",
    "precipitation_probability_max",
    "precipitation_sum",
    "temperature_2m_max",
    "temperature_2m_min",
)
FORECAST_DAYS = 16
CACHE_HOURS = 6

# A day counts as rainy when rain is likely or when a real amount is expected.
RAIN_PROBABILITY = 60
RAIN_MM = 2.0

# Where a visit mostly happens, by primary category. Mixed places (a castle with ramparts,
# a covered market) are filed under where most of the visit is spent.
OUTDOOR_CATEGORIES = {
    "park",
    "garden",
    "beach",
    "viewpoint",
    "monument",
    "landmark",
    "neighborhood",
    "market",
    "day_trip",
}


@dataclass(frozen=True)
class DayWeather:
    date: str
    weather_code: int | None
    rain_probability: int | None  # percent
    precipitation_mm: float | None
    temp_max_c: float | None
    temp_min_c: float | None

    @property
    def rainy(self) -> bool:
        likely = self.rain_probability is not None and self.rain_probability >= RAIN_PROBABILITY
        wet = self.precipitation_mm is not None and self.precipitation_mm >= RAIN_MM
        return likely or wet

    def as_dict(self) -> dict:
        return {**asdict(self), "rainy": self.rainy}


def is_outdoor(place: dict) -> bool:
    """True when the visit happens mostly outside, judged by the primary category."""
    return place["categories"][0] in OUTDOOR_CATEGORIES


def _dates(start: str, end: str) -> list[str]:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if last < first:
        raise ValueError("end date before start date")
    return [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)]


def _cache_path(cache_dir: Path, lat: float, lon: float) -> Path:
    return Path(cache_dir) / "weather" / f"{lat:.2f}_{lon:.2f}.json"


def _read_cache(path: Path, now: datetime) -> dict | None:
    if not path.exists():
        return None
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        fetched = datetime.fromisoformat(cached["fetched_at"])
    except (OSError, ValueError, KeyError):
        return None
    if now - fetched > timedelta(hours=CACHE_HOURS):
        return None
    return cached["payload"]


def _fetch(lat: float, lon: float, get) -> dict:
    resp = get(
        OPEN_METEO_URL,
        params={
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "daily": ",".join(DAILY_FIELDS),
            "timezone": "auto",
            "forecast_days": FORECAST_DAYS,
        },
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "daily" not in payload or "time" not in payload["daily"]:
        raise RuntimeError("unexpected Open-Meteo response: no daily block")
    return payload


def _parse(payload: dict) -> dict[str, DayWeather]:
    daily = payload["daily"]

    def column(name):
        return daily.get(name) or [None] * len(daily["time"])

    rows = zip(
        daily["time"],
        column("weather_code"),
        column("precipitation_probability_max"),
        column("precipitation_sum"),
        column("temperature_2m_max"),
        column("temperature_2m_min"),
        strict=True,
    )
    return {d: DayWeather(d, *values) for d, *values in rows}


def daily_forecast(
    lat: float,
    lon: float,
    start: str,
    end: str,
    cache_dir: Path,
    *,
    get=requests.get,
    now: datetime | None = None,
) -> dict[str, DayWeather | None]:
    """{date: DayWeather or None} for every trip date. None means no forecast that far out."""
    now = now or datetime.now(UTC)
    path = _cache_path(cache_dir, lat, lon)
    payload = _read_cache(path, now)
    if payload is None:
        payload = _fetch(lat, lon, get)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"fetched_at": now.isoformat(), "payload": payload}), encoding="utf-8"
        )
    by_date = _parse(payload)
    return {d: by_date.get(d) for d in _dates(start, end)}
