"""Travel times between places, computed on the fly. No routing service is called.

Walking: the straight line distance between two places, times a detour factor (streets are
not straight), at a walking speed. The routing spike (docs/routing-spike.md) checked this
against real street routing on 600 pairs of popular Lisbon places: about 1.8 minutes off per
walkable leg on average.

Transit: a fixed overhead (walk to the stop and wait) plus the distance at an average bus
and metro speed. It is a planning estimate, not a timetable, and every leg built from it is
labelled transit so the itinerary can say so.

The optimizer calls travel_legs() through ingest.catalog with the places it wants to
schedule, and gets {(from_id, to_id): {"minutes": 12.4, "mode": "walk"}} back.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

EARTH_KM = 6371.0088  # mean Earth radius
DEFAULT_SPEED_KMH = 4.5  # relaxed tourist walking pace, with stops
DEFAULT_DETOUR = 1.3  # street distance / straight line; the routing spike measured 1.23
MAX_PLACES = 2000  # a full matrix grows with the square of the number of places


@dataclass(frozen=True)
class TravelModel:
    """Every number the travel estimates depend on, in one place."""

    walk_speed_kmh: float = DEFAULT_SPEED_KMH
    walk_detour: float = DEFAULT_DETOUR
    # Average door to door speed of bus and metro in a European centre, waiting excluded.
    transit_speed_kmh: float = 15.0
    transit_detour: float = 1.4
    # Walk to the stop, wait, walk from the stop.
    transit_overhead_min: float = 10.0

    def __post_init__(self):
        if self.walk_speed_kmh <= 0 or self.transit_speed_kmh <= 0:
            raise ValueError("speeds must be > 0")
        if self.walk_detour < 1.0 or self.transit_detour < 1.0:
            raise ValueError("detour factors must be >= 1")
        if self.transit_overhead_min < 0:
            raise ValueError("transit_overhead_min must be >= 0")


def haversine_km(lat1, lon1, lat2, lon2):
    """Straight line (great circle) distance in km between every point of set 1 and set 2.

    Takes four arrays of degrees and returns a len(set 1) x len(set 2) matrix.
    """
    lat1 = np.radians(lat1)[:, None]
    lon1 = np.radians(lon1)[:, None]
    lat2 = np.radians(lat2)[None, :]
    lon2 = np.radians(lon2)[None, :]
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _distances_km(places: list[dict]) -> np.ndarray:
    lat = np.array([p["lat"] for p in places], dtype=float)
    lon = np.array([p["lon"] for p in places], dtype=float)
    return haversine_km(lat, lon, lat, lon)


def walking_matrix(places: list[dict], model: TravelModel | None = None) -> np.ndarray:
    """minutes[i][j] to walk from places[i] to places[j]."""
    model = model or TravelModel()
    minutes = _distances_km(places) * model.walk_detour / model.walk_speed_kmh * 60.0
    np.fill_diagonal(minutes, 0.0)
    return minutes


def transit_matrix(places: list[dict], model: TravelModel | None = None) -> np.ndarray:
    """minutes[i][j] by bus or metro: the fixed overhead plus the ride."""
    model = model or TravelModel()
    ride = _distances_km(places) * model.transit_detour / model.transit_speed_kmh * 60.0
    minutes = model.transit_overhead_min + ride
    np.fill_diagonal(minutes, 0.0)
    return minutes


def travel_legs(
    places: list[dict], max_walk_minutes: float, model: TravelModel | None = None
) -> dict[tuple[str, str], dict]:
    """{(from_id, to_id): {"minutes": float, "mode": "walk" | "transit"}} for every ordered pair.

    A leg is walk when it takes at most max_walk_minutes on foot, otherwise transit, even
    when transit is a little slower: the tolerance is the traveler saying how far they are
    willing to walk. Pairs of a place with itself are left out.
    """
    if not places:
        return {}
    if len(places) > MAX_PLACES:
        raise ValueError(
            f"{len(places)} places is too many (max {MAX_PLACES}); select candidates first"
        )
    model = model or TravelModel()
    walk = walking_matrix(places, model)
    transit = transit_matrix(places, model)
    ids = [p["id"] for p in places]
    legs: dict[tuple[str, str], dict] = {}
    for i, a in enumerate(ids):
        for j, b in enumerate(ids):
            if i == j:
                continue
            if walk[i, j] <= max_walk_minutes:
                legs[(a, b)] = {"minutes": round(float(walk[i, j]), 1), "mode": "walk"}
            else:
                legs[(a, b)] = {"minutes": round(float(transit[i, j]), 1), "mode": "transit"}
    return legs
