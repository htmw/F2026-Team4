"""Tests for the routing spike maths and report."""

import numpy as np
import pytest

from ingest.matrix import haversine_km
from ingest.routing_spike import compare, osrm_table, pick_sample, render

KM_PER_DEG_LAT = 111.195


def _grid(n=5, step_km=0.6):
    return [
        {
            "id": f"osm:node/{i}",
            "lat": 38.72 + (i % 3) * step_km / KM_PER_DEG_LAT,
            "lon": -9.14 + (i // 3) * step_km / (KM_PER_DEG_LAT * 0.78),
            "popularity": 1.0 - i / 100,
        }
        for i in range(n)
    ]


def _table(places, ratio, speed_kmh):
    lat = np.array([p["lat"] for p in places])
    lon = np.array([p["lon"] for p in places])
    km = haversine_km(lat, lon, lat, lon)
    return {
        "ids": [p["id"] for p in places],
        "distances": (km * ratio * 1000).tolist(),
        "durations": (km * ratio / speed_kmh * 3600).tolist(),
    }


def test_compare_recovers_the_detour_and_speed():
    places = _grid()
    result = compare(places, _table(places, ratio=1.25, speed_kmh=5.0), speed_kmh=4.5)

    assert result["pairs"] == 20
    assert result["detour_ratio"]["median"] == pytest.approx(1.25, abs=1e-3)
    assert result["osrm_implied_speed_kmh"] == pytest.approx(5.0, abs=0.01)
    default, calibrated = result["methods"].values()
    assert calibrated["detour_factor"] == pytest.approx(1.25, abs=1e-3)
    assert calibrated["vs_street_distance"]["mae_min"] == pytest.approx(0.0, abs=0.01)
    assert default["detour_factor"] == 1.3
    assert default["vs_street_distance"]["bias_min"] > 0  # 1.3 overestimates a 1.25 city


def test_compare_skips_missing_routes():
    places = _grid(3)
    table = _table(places, ratio=1.2, speed_kmh=5.0)
    table["durations"][0][1] = None

    assert compare(places, table)["pairs"] == 5


def test_render_states_a_verdict():
    places = _grid()
    result = compare(places, _table(places, ratio=1.25, speed_kmh=5.0))
    text = render("Lisbon", result, "test server", "2026-10-17")

    assert "| OSRM walking | (reference) |" in text
    assert "Good enough?" in text
    assert "Keep haversine x 1.3" in text
    assert "the same as the 4.5 km/h" not in text  # OSRM was 5 km/h in this table


def test_pick_sample_is_stable_and_uses_popular_places():
    places = _grid(40)
    first = pick_sample(places, n=5, pool=10, seed=3)
    second = pick_sample(places, n=5, pool=10, seed=3)

    assert first == second
    assert all(int(p["id"].split("/")[1]) < 10 for p in first)


def test_osrm_table_requests_durations_and_distances():
    seen = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"code": "Ok", "durations": [[0, 60], [60, 0]], "distances": [[0, 80], [80, 0]]}

    def fake_get(url, params, timeout):
        seen["url"], seen["params"] = url, params
        return Response()

    places = _grid(2)
    table = osrm_table(places, "https://osrm.test/routed-foot/", get=fake_get)

    assert seen["url"].startswith("https://osrm.test/routed-foot/table/v1/foot/-9.14,")
    assert seen["params"] == {"annotations": "duration,distance"}
    assert table["ids"] == ["osm:node/0", "osm:node/1"]
