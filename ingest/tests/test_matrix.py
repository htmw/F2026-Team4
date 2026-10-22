"""Tests for the travel time estimates."""

import numpy as np
import pytest

from ingest.matrix import (
    MAX_PLACES,
    TravelModel,
    haversine_km,
    transit_matrix,
    travel_legs,
    walking_matrix,
)

KM_PER_DEG_LAT = 111.195  # mean Earth radius, the value haversine_km uses


def _place(pid, lat, lon):
    return {"id": pid, "lat": lat, "lon": lon}


def _line(n, step_km=1.0):
    """n places in Lisbon, due north of each other, step_km apart."""
    return [_place(f"p{i}", 38.72 + i * step_km / KM_PER_DEG_LAT, -9.14) for i in range(n)]


def test_haversine_one_degree_of_latitude():
    km = haversine_km(np.array([38.0]), np.array([-9.0]), np.array([39.0]), np.array([-9.0]))

    assert km[0, 0] == pytest.approx(KM_PER_DEG_LAT, rel=1e-3)


def test_walking_matrix_values_symmetry_and_diagonal():
    m = walking_matrix(_line(3), TravelModel(walk_speed_kmh=4.5, walk_detour=1.3))

    assert m.shape == (3, 3)
    assert np.allclose(np.diag(m), 0.0)
    assert np.allclose(m, m.T)
    # 1 km straight line, 1.3 detour, 4.5 km/h -> 17.3 minutes.
    assert m[0, 1] == pytest.approx(1.3 / 4.5 * 60, rel=1e-3)
    assert m[0, 2] == pytest.approx(2 * 1.3 / 4.5 * 60, rel=1e-3)


def test_walking_matrix_handles_no_places():
    assert walking_matrix([]).shape == (0, 0)


def test_transit_matrix_adds_overhead_to_distance_time():
    model = TravelModel(transit_speed_kmh=15, transit_detour=1.4, transit_overhead_min=10)
    m = transit_matrix(_line(2, step_km=3.0), model)

    assert m[0, 0] == 0.0
    assert m[0, 1] == pytest.approx(10 + 3 * 1.4 / 15 * 60, rel=1e-3)


def test_travel_legs_walks_short_hops_and_rides_long_ones():
    places = _line(3, step_km=1.0)
    legs = travel_legs(places, max_walk_minutes=20)

    assert len(legs) == 6  # ordered pairs, no self pairs
    assert legs[("p0", "p1")]["mode"] == "walk"
    assert legs[("p0", "p1")]["minutes"] == pytest.approx(17.3, abs=0.1)
    assert legs[("p0", "p2")]["mode"] == "transit"
    assert legs[("p2", "p0")] == legs[("p0", "p2")]


def test_travel_legs_respects_a_zero_walking_tolerance():
    legs = travel_legs(_line(2, step_km=0.2), max_walk_minutes=0)

    assert legs[("p0", "p1")]["mode"] == "transit"


def test_travel_legs_empty_input():
    assert travel_legs([], max_walk_minutes=20) == {}


def test_travel_legs_refuses_a_whole_city():
    with pytest.raises(ValueError, match="select candidates first"):
        travel_legs(_line(MAX_PLACES + 1, step_km=0.001), max_walk_minutes=20)


def test_travel_model_validates_numbers():
    with pytest.raises(ValueError):
        TravelModel(walk_speed_kmh=0)
    with pytest.raises(ValueError):
        TravelModel(walk_detour=0.9)
    with pytest.raises(ValueError):
        TravelModel(transit_detour=0.5)
    with pytest.raises(ValueError):
        TravelModel(transit_overhead_min=-1)
