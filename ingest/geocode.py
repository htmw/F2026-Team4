"""City name -> destination + bounding box, via Nominatim. Cached per city."""

from __future__ import annotations

import math
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


# A destination wider or taller than this is almost certainly a region or a country, not a
# city. London (about 58 x 47 km) fits, Italy does not. Pass an explicit bbox to go bigger.
DEFAULT_MAX_SPAN_KM = 80.0
_KM_PER_DEG_LAT = 111.32


class GeocodeError(RuntimeError):
    """Raised when a destination cannot be geocoded or validated."""


def bbox_span_km(bbox) -> tuple[float, float]:
    """Return (width_km, height_km) of a south, west, north, east box.

    A degree of longitude shrinks with latitude, so the width uses the cosine of the
    middle latitude. That is accurate to well under 1% at city scale.
    """
    south, west, north, east = bbox
    mid_lat = math.radians((south + north) / 2)
    width = (east - west) * _KM_PER_DEG_LAT * math.cos(mid_lat)
    height = (north - south) * _KM_PER_DEG_LAT
    return width, height


@dataclass(frozen=True)
class Geocoded:
    query: str
    name: str
    country: str  # ISO 3166-1 alpha-2, uppercase; "" if unavailable
    lat: float
    lon: float
    bbox: tuple[float, float, float, float]  # south, west, north, east
    display_name: str
    country_name: str = ""  # in English, e.g. "Italy"; "" if unavailable
    kind: str = ""  # Nominatim's addresstype: city, town, state, country...

    def box_around_centre(self, radius_km: float) -> tuple[float, float, float, float]:
        """A square reaching radius_km from the centre each way: the walkable middle."""
        dlat = radius_km / _KM_PER_DEG_LAT
        dlon = dlat / math.cos(math.radians(self.lat))
        return (self.lat - dlat, self.lon - dlon, self.lat + dlat, self.lon + dlon)

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
    max_span_km: float | None = DEFAULT_MAX_SPAN_KM,
    settlements_only: bool = True,
) -> Geocoded:
    """Resolve a destination using Nominatim and cache the result.

    max_span_km guards against a query that resolves to a whole region. The pipeline passes
    None when the caller supplies an explicit bbox, because then the geocoded box is only
    used for the name, country and centre point.
    """
    # Settlements only: without it "newyork" matched a shop called NEWYORK in Tokyo. The
    # open search is only used to tell a traveler that "japan" is a country.
    feature = {"featureType": "settlement"} if settlements_only else {}
    key = {"query": query.strip().lower(), **feature}
    file_name = "geocode.json" if settlements_only else "geocode_any.json"
    path = Path(cache_dir) / slugify(query) / file_name
    wrapper = None if refresh else load_cached(path, key)

    if wrapper is None:
        resp = get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": 1,
                **feature,
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

    # Pass max_span_km=None to disable the area-size restriction.
    if max_span_km is not None:
        width, height = bbox_span_km((south, west, north, east))
        if width > max_span_km or height > max_span_km:
            raise GeocodeError(
                f"{query!r} resolved to an area of {width:.0f} x {height:.0f} km, "
                "which is too large for a city. Be more specific "
                "or pass an explicit --bbox."
            )

    address = r.get("address") or {}
    return Geocoded(
        query=query,
        name=r.get("name") or query.strip(),
        country=(address.get("country_code") or "").upper(),
        lat=float(r["lat"]),
        lon=float(r["lon"]),
        bbox=(south, west, north, east),
        display_name=r.get("display_name", ""),
        country_name=address.get("country") or "",
        kind=r.get("addresstype") or "",
    )
