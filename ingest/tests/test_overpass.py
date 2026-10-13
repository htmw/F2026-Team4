"""Tests for Overpass query building, retries, and caching."""

from pathlib import Path

import pytest
import requests

from ingest.cache import load_cached
from ingest.overpass import (
    BACKOFFS,
    ENDPOINTS,
    GROUPS,
    REQUEST_TIMEOUT,
    build_query,
    fetch_group,
    fetch_overpass,
)

BBOX = (38.70, -9.20, 38.80, -9.10)


class FakeResponse:
    """Small fake HTTP response for tests."""

    def __init__(self, payload=None, error=None):
        self.payload = payload or {"elements": []}
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


def test_build_query_formats_bounding_box():
    query = build_query(GROUPS["sights"], BBOX)

    assert "[out:json][timeout:120];" in query
    assert "38.700000,-9.200000,38.800000,-9.100000" in query
    assert '"tourism"' in query


def test_fetch_overpass_returns_successful_payload():
    calls = []

    def fake_post(url, *, data, timeout, headers=None):
        calls.append((url, data, timeout))
        return FakeResponse({"elements": [{"id": 123}]})

    payload, endpoint = fetch_overpass(
        "test query",
        "test",
        post=fake_post,
        sleep=lambda _: None,
        log=lambda _: None,
    )

    assert payload == {"elements": [{"id": 123}]}
    assert endpoint == ENDPOINTS[0]
    assert len(calls) == 1
    assert calls[0][1] == {"data": "test query"}
    assert calls[0][2] == REQUEST_TIMEOUT


def test_fetch_overpass_retries_after_endpoint_failures():
    calls = []
    sleeps = []

    def fake_post(url, *, data, timeout, headers=None):
        calls.append(url)
        if len(calls) <= len(ENDPOINTS):
            raise requests.ConnectionError("server unavailable")
        return FakeResponse({"elements": []})

    payload, endpoint = fetch_overpass(
        "test query",
        "test",
        post=fake_post,
        sleep=sleeps.append,
        log=lambda _: None,
    )

    assert payload == {"elements": []}
    assert endpoint == ENDPOINTS[0]
    assert len(calls) == len(ENDPOINTS) + 1
    assert sleeps == [BACKOFFS[0]]


def test_fetch_overpass_rejects_invalid_payload():
    def fake_post(url, *, data, timeout, headers=None):
        return FakeResponse({"unexpected": []})

    with pytest.raises(RuntimeError, match="exhausted all attempts"):
        fetch_overpass(
            "test query",
            "test",
            post=fake_post,
            sleep=lambda _: None,
            log=lambda _: None,
        )


def test_fetch_group_caches_successful_response(tmp_path: Path):
    calls = []

    def fake_post(url, *, data, timeout, headers=None):
        calls.append(url)
        return FakeResponse({"elements": [{"id": 456}]})

    first = fetch_group(
        "sights",
        BBOX,
        tmp_path,
        "lisbon",
        post=fake_post,
        sleep=lambda _: None,
        log=lambda _: None,
    )

    second = fetch_group(
        "sights",
        BBOX,
        tmp_path,
        "lisbon",
        post=lambda *args, **kwargs: pytest.fail("Cache should prevent another request"),
        sleep=lambda _: None,
        log=lambda _: None,
    )

    assert first == second
    assert first["payload"] == {"elements": [{"id": 456}]}
    assert len(calls) == 1

    cache_path = tmp_path / "lisbon" / "overpass_sights.json"
    assert load_cached(cache_path, first["key"]) == first


def test_fetch_group_refresh_bypasses_cache(tmp_path: Path):
    calls = []

    def fake_post(url, *, data, timeout, headers=None):
        calls.append(url)
        return FakeResponse({"elements": [{"id": len(calls)}]})

    fetch_group(
        "sights",
        BBOX,
        tmp_path,
        "lisbon",
        post=fake_post,
        sleep=lambda _: None,
        log=lambda _: None,
    )

    refreshed = fetch_group(
        "sights",
        BBOX,
        tmp_path,
        "lisbon",
        refresh=True,
        post=fake_post,
        sleep=lambda _: None,
        log=lambda _: None,
    )

    assert len(calls) == 2
    assert refreshed["payload"] == {"elements": [{"id": 2}]}
