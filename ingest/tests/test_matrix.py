"""Tests for the travel time matrices and the OSRM comparison helpers."""

import numpy as np
import pytest

from ingest.matrix import (
    TravelModel,
    haversine_km,
    matrix_payload,
    osrm_sample,
    select_for_matrix,
    summarize_osrm,
    transit_matrix,
    travel_legs,
    walking_matrix,
)

KM_PER_DEG_LAT = 111.195  # mean Earth radius, the value haversine_km uses


def _place(pid, lat, lon, popularity=0.0):
    return {"id": pid, "lat": lat, "lon": lon, "popularity": popularity}


def _line(n, step_km=1.0):
    """n places due north of each other, step_km apart."""
    return [_place(f"p{i}", 41.9 + i * step_km / KM_PER_DEG_LAT, 12.5) for i in range(n)]


def test_haversine_one_degree_of_latitude():
    km = haversine_km(np.array([41.0]), np.array([12.0]), np.array([42.0]), np.array([12.0]))

    assert km[0, 0] == pytest.approx(KM_PER_DEG_LAT, rel=1e-3)


def test_walking_matrix_values_symmetry_and_diagonal():
    m = walking_matrix(_line(3), speed_kmh=4.5, detour_factor=1.3)

    assert m.shape == (3, 3)
    assert np.allclose(np.diag(m), 0.0)
    assert np.allclose(m, m.T)
    # 1 km straight line, 1.3 detour, 4.5 km/h -> 17.3 minutes.
    assert m[0, 1] == pytest.approx(1.3 / 4.5 * 60, rel=1e-3)
    assert m[0, 2] == pytest.approx(2 * 1.3 / 4.5 * 60, rel=1e-3)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"speed_kmh": 0}, "speed_kmh"),
        ({"detour_factor": 0.9}, "detour_factor"),
        ({"max_places": 2}, "too many"),
    ],
)
def test_walking_matrix_rejects_bad_input(kwargs, message):
    with pytest.raises(ValueError, match=message):
        walking_matrix(_line(3), **kwargs)


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


def test_travel_model_validates_numbers():
    with pytest.raises(ValueError):
        TravelModel(walk_speed_kmh=0)
    with pytest.raises(ValueError):
        TravelModel(transit_detour=0.5)
    with pytest.raises(ValueError):
        TravelModel(transit_overhead_min=-1)


def test_select_for_matrix_keeps_most_popular_then_id_order():
    places = [_place("b", 0, 0, 0.5), _place("a", 0, 0, 0.5), _place("c", 0, 0, 0.9)]

    assert [p["id"] for p in select_for_matrix(places, 2)] == ["c", "a"]


def test_matrix_payload_shape_with_transit():
    places = _line(2)
    model = TravelModel()
    payload = matrix_payload(
        places,
        walking_matrix(places),
        4.5,
        1.3,
        transit=transit_matrix(places, model),
        model=model,
    )

    assert payload["ids"] == ["p0", "p1"]
    assert payload["mode"] == "walk"
    assert len(payload["minutes"]) == 2
    assert len(payload["transit_minutes"]) == 2
    assert payload["transit_model"]["transit_overhead_min"] == 10.0


def _osrm_minutes(places, ratio, speed_kmh):
    lat = np.array([p["lat"] for p in places])
    lon = np.array([p["lon"] for p in places])
    km = haversine_km(lat, lon, lat, lon)
    return (km * ratio / speed_kmh * 60).tolist()


def test_summarize_osrm_recovers_the_detour_factor():
    places = _line(4)
    summary = summarize_osrm(places, _osrm_minutes(places, 1.25, 4.5), speed_kmh=4.5)

    assert summary["n_pairs"] == 12
    assert summary["median_ratio"] == pytest.approx(1.25, abs=1e-3)
    assert summary["rejected"] is False


def test_summarize_osrm_rejects_car_speeds():
    places = _line(4)
    summary = summarize_osrm(places, _osrm_minutes(places, 1.0, 40.0), speed_kmh=4.5)

    assert summary["rejected"] is True


def test_osrm_sample_builds_lon_lat_url_and_converts_seconds():
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"code": "Ok", "durations": [[0, 600], [600, 0]]}

    def fake_get(url, params, timeout):
        calls.append(url)
        return Response()

    places = [_place("a", 41.9, 12.5), _place("b", 41.91, 12.51)]
    sample, minutes = osrm_sample(places, "http://osrm.test/", n=2, get=fake_get)

    assert calls[0] == "http://osrm.test/table/v1/walking/12.5,41.9;12.51,41.91"
    assert [p["id"] for p in sample] == ["a", "b"]
    assert minutes == [[0.0, 10.0], [10.0, 0.0]]


def test_osrm_sample_raises_on_a_bad_response():
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"code": "TooBig"}

    with pytest.raises(RuntimeError, match="TooBig"):
        osrm_sample(_line(2), "http://osrm.test", get=lambda *a, **k: Response())
