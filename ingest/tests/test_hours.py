"""Tests for the ingestion opening-hours parser."""

from ingest.hours import parse_opening_hours


def test_missing_hours_are_absent():
    assert parse_opening_hours(None).status == "absent"
    assert parse_opening_hours("").status == "absent"
    assert parse_opening_hours("   ").status == "absent"


def test_weekday_hours_are_parsed():
    result = parse_opening_hours("Mo-Fr 09:00-17:00")

    assert result.status == "parsed"
    assert result.hours["confidence"] == "known"

    for day in ("mon", "tue", "wed", "thu", "fri"):
        assert result.hours[day] == [["09:00", "17:00"]]

    assert result.hours["sat"] is None
    assert result.hours["sun"] is None


def test_closed_day_is_not_open():
    result = parse_opening_hours("Mo-Fr 09:00-17:00; Sa-Su off")

    assert result.status == "parsed"
    assert result.hours["sat"] is None
    assert result.hours["sun"] is None


def test_overnight_hours_continue_into_next_day():
    result = parse_opening_hours("Mo 22:00-02:00")

    assert result.status == "parsed"
    assert result.hours["mon"] == [["22:00", "23:59"]]
    assert result.hours["tue"] == [["00:00", "02:00"]]


def test_holiday_only_rules_are_not_marked_known():
    result = parse_opening_hours("PH off")

    assert result.status == "unparseable"
    assert result.hours is None
    assert result.reason is not None


def test_holiday_rules_are_reported_as_ignored():
    result = parse_opening_hours("Mo-Fr 09:00-17:00; PH 10:00-12:00")

    assert result.status == "parsed"
    assert result.ignored == ["PH: 10:00-12:00"]

    for day in ("mon", "tue", "wed", "thu", "fri"):
        assert result.hours[day] == [["09:00", "17:00"]]

    assert result.hours["sat"] is None
    assert result.hours["sun"] is None
