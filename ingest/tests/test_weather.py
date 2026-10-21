"""Tests for the trip weather helper."""

from datetime import UTC, datetime, timedelta

import pytest

from ingest.weather import DayWeather, daily_forecast, is_outdoor

NOW = datetime(2026, 11, 9, 8, 0, tzinfo=UTC)

PAYLOAD = {
    "latitude": 41.89,
    "longitude": 12.48,
    "daily_units": {"precipitation_sum": "mm"},
    "daily": {
        "time": ["2026-11-09", "2026-11-10", "2026-11-11"],
        "weather_code": [3, 63, 1],
        "precipitation_probability_max": [10, 85, 30],
        "precipitation_sum": [0.0, 7.4, 2.5],
        "temperature_2m_max": [18.2, 15.1, 17.0],
        "temperature_2m_min": [10.1, 11.3, 9.0],
    },
}


class _Response:
    def raise_for_status(self):
        pass

    def json(self):
        return PAYLOAD


@pytest.fixture
def calls():
    return []


@pytest.fixture
def fake_get(calls):
    def get(url, params, timeout):
        calls.append(params)
        return _Response()

    return get


def test_forecast_marks_rainy_days(tmp_path, fake_get):
    days = daily_forecast(41.89, 12.48, "2026-11-09", "2026-11-11", tmp_path, get=fake_get, now=NOW)

    assert days["2026-11-09"].rainy is False
    assert days["2026-11-10"].rainy is True  # 85 percent and 7.4 mm
    assert days["2026-11-11"].rainy is True  # only 30 percent, but 2.5 mm expected


def test_dates_past_the_forecast_are_none(tmp_path, fake_get):
    days = daily_forecast(41.89, 12.48, "2026-11-11", "2026-11-12", tmp_path, get=fake_get, now=NOW)

    assert days["2026-11-11"] is not None
    assert days["2026-11-12"] is None


def test_forecast_is_cached_for_a_few_hours(tmp_path, fake_get, calls):
    for hours in (0, 2):
        daily_forecast(
            41.89, 12.48, "2026-11-09", "2026-11-09", tmp_path,
            get=fake_get, now=NOW + timedelta(hours=hours),
        )
    assert len(calls) == 1

    daily_forecast(
        41.89, 12.48, "2026-11-09", "2026-11-09", tmp_path,
        get=fake_get, now=NOW + timedelta(hours=7),
    )
    assert len(calls) == 2


def test_request_asks_for_the_daily_fields(tmp_path, fake_get, calls):
    daily_forecast(41.89, 12.48, "2026-11-09", "2026-11-09", tmp_path, get=fake_get, now=NOW)

    assert "precipitation_probability_max" in calls[0]["daily"]
    assert calls[0]["timezone"] == "auto"


def test_missing_values_do_not_count_as_rain():
    day = DayWeather("2026-11-09", None, None, None, None, None)

    assert day.rainy is False
    assert day.as_dict()["rainy"] is False


@pytest.mark.parametrize(
    "categories, outdoor",
    [(["park"], True), (["landmark", "museum"], True), (["museum", "landmark"], False),
     (["restaurant"], False), (["church"], False), (["viewpoint"], True)],
)
def test_is_outdoor_uses_the_primary_category(categories, outdoor):
    assert is_outdoor({"categories": categories}) is outdoor
