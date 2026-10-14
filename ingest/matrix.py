"""Travel-time matrix: haversine x detour factor / walking speed, plus an OSRM cross-check.

PROPOSAL, not yet a contract: the JSON shape below needs agreement with the Optimizer team.
"""

from __future__ import annotations

import numpy as np
import requests

EARTH_KM = 6371.0088
DEFAULT_SPEED_KMH = 4.5
DEFAULT_DETOUR = 1.3  # street distance / straight-line. A starting guess; the spike measures it.


def haversine_km(lat1, lon1, lat2, lon2):
    """Pairwise great-circle distance (km) between two sets of points given in degrees."""
    lat1 = np.radians(lat1)[:, None]
    lon1 = np.radians(lon1)[:, None]
    lat2 = np.radians(lat2)[None, :]
    lon2 = np.radians(lon2)[None, :]
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _latlon(places):
    return (
        np.array([p["lat"] for p in places], dtype=float),
        np.array([p["lon"] for p in places], dtype=float),
    )


def walking_matrix(
    places: list[dict],
    speed_kmh: float = DEFAULT_SPEED_KMH,
    detour_factor: float = DEFAULT_DETOUR,
    max_places: int = 2000,
) -> np.ndarray:
    """minutes[i][j] to walk from places[i] to places[j]."""
    if speed_kmh <= 0:
        raise ValueError("speed_kmh must be > 0")
    if detour_factor < 1.0:
        raise ValueError("detour_factor must be >= 1 (street distance cannot beat a straight line)")
    if len(places) > max_places:
        raise ValueError(
            f"{len(places)} places is too many for a full matrix (max {max_places}); "
            "select candidates first"
        )
    lat, lon = _latlon(places)
    m = haversine_km(lat, lon, lat, lon) * detour_factor / speed_kmh * 60.0
    np.fill_diagonal(m, 0.0)
    return m


def select_for_matrix(places: list[dict], prominence: dict[str, int], n: int) -> list[dict]:
    """Interim cap: most-documented places first. Real flow: matrix over ranked candidates."""
    return sorted(places, key=lambda p: (-prominence.get(p["id"], 0), p["id"]))[:n]


def matrix_payload(
    places: list[dict], minutes: np.ndarray, speed_kmh: float, detour_factor: float
) -> dict:
    return {
        "method": "haversine",
        "unit": "minutes",
        "mode": "walk",
        "speed_kmh": speed_kmh,
        "detour_factor": detour_factor,
        "ids": [p["id"] for p in places],
        "minutes": np.round(minutes, 1).tolist(),
    }


def osrm_sample(
    places: list[dict],
    base_url: str,
    n: int = 25,
    seed: int = 0,
    timeout: int = 25,
    get=requests.get,
):
    """One OSRM /table call on a random sample. Returns (sample_places, minutes_matrix).

    Use a self-hosted OSRM with a foot profile: the public demo server routes
    'walking' requests at car-like speeds, which summarize_osrm will reject.
    """
    if len(places) < 2:
        raise ValueError("need at least 2 places")
    rng = np.random.default_rng(seed)
    idx = sorted(rng.choice(len(places), size=min(n, len(places)), replace=False).tolist())
    sample = [places[i] for i in idx]
    coords = ";".join(f"{p['lon']},{p['lat']}" for p in sample)
    resp = get(
        f"{base_url.rstrip('/')}/table/v1/walking/{coords}",
        params={"annotations": "duration"},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "Ok" or "durations" not in data:
        raise RuntimeError(f"bad OSRM response: code={data.get('code')}")
    return sample, [[None if d is None else d / 60.0 for d in row] for row in data["durations"]]


def summarize_osrm(
    sample: list[dict],
    minutes,
    speed_kmh: float = DEFAULT_SPEED_KMH,
    max_plausible_kmh: float = 8.0,
) -> dict:
    """Compare OSRM durations with straight-line time at `speed_kmh`.

    median_ratio is the detour_factor that makes our matrix match OSRM on average.
    Results are flagged `rejected` if the implied straight-line speed is implausible for walking.
    """
    lat, lon = _latlon(sample)
    km = haversine_km(lat, lon, lat, lon)
    ratios, speeds = [], []
    for i in range(len(sample)):
        for j in range(len(sample)):
            t = minutes[i][j]
            if i == j or t is None or t <= 0 or km[i, j] <= 0:
                continue
            ratios.append(t / (km[i, j] / speed_kmh * 60.0))
            speeds.append(km[i, j] / (t / 60.0))
    if not ratios:
        return {"n_pairs": 0, "rejected": True, "note": "no usable pairs"}
    med_speed = float(np.median(speeds))
    out = {
        "n_pairs": len(ratios),
        "median_ratio": round(float(np.median(ratios)), 3),
        "mean_ratio": round(float(np.mean(ratios)), 3),
        "p90_ratio": round(float(np.percentile(ratios, 90)), 3),
        "median_straightline_speed_kmh": round(med_speed, 2),
        "rejected": med_speed > max_plausible_kmh,
    }
    out["note"] = (
        "rejected: implausible walking speeds (routing server not using a foot profile)"
        if out["rejected"]
        else f"suggested detour_factor ~ {out['median_ratio']} at {speed_kmh} km/h"
    )
    return out
