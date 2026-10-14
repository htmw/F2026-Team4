"""City name -> destination + bounding box, via Nominatim. Cached per city."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import requests

from .cache import load_cached, slugify, store

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Nominatim's policy requires an identifying User-Agent.
# Put your contact in the environment variable.
USER_AGENT = os.environ.get(
    "WANDERWISE_USER_AGENT",
    "Wanderwise-Capstone/1.0 (student project)",
)


class GeocodeError(RuntimeError):
    """Raised when a destination cannot be geocoded or validated."""


@dataclass(frozen=True)
class Geocoded:
    query: str
    name: str
    country: str  # ISO 3166-1 alpha-2, uppercase; "" if unavailable
    lat: float
    lon: float
    bbox: tuple[float, float, float, float]  # south, west, north, east
    display_name: str

    def destination(self) -> dict:
        """Return the destination shape used by the Itinerary contract."""
        return {
            "name": self.name,
            "country": self.country,
            "lat": self.lat,
            "lon": self.lon,
        }


def parse_bbox(text: str) -> tuple[float, float, float, float]:
    """Parse and validate a bounding box in south,west,north,east order."""
    try:
        south, west, north, east = (float(value) for value in text.split(","))
    except ValueError as exc:
        raise ValueError("bbox must be 'south,west,north,east'") from exc

    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise ValueError(f"invalid bbox: {text}")

    return south, west, north, east


def geocode(
    query: str,
    cache_dir: Path,
    *,
    refresh: bool = False,
    get=requests.get,
    max_span_deg: float | None = 0.8,
) -> Geocoded:
    """Resolve a destination using Nominatim and cache the result."""
    key = {"query": query.strip().lower()}
    path = Path(cache_dir) / slugify(query) / "geocode.json"
    wrapper = None if refresh else load_cached(path, key)

    if wrapper is None:
        resp = get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": 1,
            },
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "en",
            },
            timeout=30,
        )
        resp.raise_for_status()
        wrapper = store(path, key, resp.json())

    results = wrapper["payload"]

    if not results:
        raise GeocodeError(f"No geocoding result for {query!r}. Try 'City, Country'.")

    r = results[0]
    south, north, west, east = (float(value) for value in r["boundingbox"])

    # Pass max_span_deg=None to disable the area-size restriction.
    if max_span_deg is not None and (
        (north - south) > max_span_deg or (east - west) > max_span_deg
    ):
        raise GeocodeError(
            f"{query!r} resolved to an area of "
            f"{north - south:.2f} x {east - west:.2f} degrees, "
            "which is too large for a city. Be more specific "
            "or pass an explicit --bbox."
        )

    return Geocoded(
        query=query,
        name=r.get("name") or query.strip(),
        country=(r.get("address", {}).get("country_code") or "").upper(),
        lat=float(r["lat"]),
        lon=float(r["lon"]),
        bbox=(south, west, north, east),
        display_name=r.get("display_name", ""),
    )
