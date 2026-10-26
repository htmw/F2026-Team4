
"""Travel-time estimates and optional matrix lookup."""

from math import atan2, cos, radians, sin, sqrt
from typing import Any


def distance_km(
    first: dict[str, Any],
    second: dict[str, Any],
) -> float:
    """Haversine distance in kilometers."""
    lat1 = radians(float(first["lat"]))
    lon1 = radians(float(first["lon"]))
    lat2 = radians(float(second["lat"]))
    lon2 = radians(float(second["lon"]))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        sin(dlat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    )

    return 6371.0 * 2 * atan2(
        sqrt(a), sqrt(max(0.0, 1.0 - a))
    )


def travel_between(
    first: dict[str, Any] | None,
    second: dict[str, Any],
    max_walk_minutes: int,
    matrix: dict | None = None,
) -> tuple[int, str, bool]:
    """
    Returns (minutes, mode, estimated).

    The matrix may contain:
      (from_id, to_id): {"minutes": 12, "mode": "walk"}

    Without matrix data, uses approximate travel times.
    """
    if first is None:
        return 0, "none", False

    key = (first["id"], second["id"])

    if matrix is not None and key in matrix:
        leg = matrix[key]
        minutes = float(leg["minutes"])
        mode = leg["mode"]

        if mode == "walk" and minutes > max_walk_minutes:
            return -1, "none", False

        if minutes < 0:
            raise ValueError("Negative travel time")

        # The Data team's legs are estimates too (no live routing), unless a leg says so.
        return round(minutes), mode, bool(leg.get("estimated", True))

    straight_km = distance_km(first, second)

    # Approximation only, not a routing engine.
    walking_minutes = round(
        straight_km * 1.3 / 4.5 * 60
    )

    if walking_minutes <= max_walk_minutes:
        return walking_minutes, "walk", True

    # Assumed road detour, 20 km/h plus waiting time.
    transit_minutes = round(
        straight_km * 1.4 / 20 * 60 + 10
    )

    return max(1, transit_minutes), "transit", True
