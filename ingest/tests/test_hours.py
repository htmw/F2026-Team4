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


def test_closed_days_alone_do_not_mean_closed_all_week():
    for value in ("Su off", "Mo off", "Sa,Su closed"):
        result = parse_opening_hours(value)

        assert result.status == "unparseable", value
        assert result.hours is None


def test_closed_every_day_is_known_when_every_day_is_named():
    for value in ("off", "Mo-Su off", "Mo-Fr off; Sa-Su off"):
        result = parse_opening_hours(value)

        days = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        assert result.status == "parsed", value
        assert all(result.hours[d] is None for d in days)


def test_hours_past_midnight_written_as_26_00():
    result = parse_opening_hours("Fr-Sa 19:00-26:00")

    assert result.status == "parsed"
    assert result.hours["fri"] == [["19:00", "23:59"]]
    assert result.hours["sat"] == [["00:00", "02:00"], ["19:00", "23:59"]]
    assert result.hours["sun"] == [["00:00", "02:00"]]
    assert parse_opening_hours("Mo 10:00-35:00").status == "unparseable"


def test_rules_joined_by_a_comma_add_to_each_other():
    result = parse_opening_hours("Mo-Fr 09:00-12:00, We 14:00-18:00, Sa 10:00-14:00")

    assert result.status == "parsed"
    assert result.hours["mon"] == [["09:00", "12:00"]]
    assert result.hours["wed"] == [["09:00", "12:00"], ["14:00", "18:00"]]
    assert result.hours["sat"] == [["10:00", "14:00"]]
    assert result.hours["sun"] is None


def test_a_day_list_is_not_mistaken_for_an_added_rule():
    result = parse_opening_hours("Mo,We 10:00-12:00")

    assert result.hours["mon"] == result.hours["wed"] == [["10:00", "12:00"]]
    assert result.hours["tue"] is None


def test_seasonal_hours_stay_unknown():
    assert parse_opening_hours("Apr-Oct Mo-Su 09:00-18:00").status == "unparseable"
