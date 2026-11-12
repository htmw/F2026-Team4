
"""Scheduling constraints and time helpers."""

from datetime import date, timedelta
from typing import Any


def to_minutes(hhmm: str) -> int:
    hour, minute = map(int, hhmm.split(":"))
    return hour * 60 + minute


def to_hhmm(value: int) -> str:
    if not 0 <= value < 1440:
        raise ValueError("Time is outside one calendar day")
    return f"{value // 60:02d}:{value % 60:02d}"


def date_range(start: str, end: str) -> list[str]:
    first = date.fromisoformat(start)
    last = date.fromisoformat(end)

    if last < first:
        raise ValueError("End date cannot precede start date")

    return [
        (first + timedelta(days=i)).isoformat()
        for i in range((last - first).days + 1)
    ]


def available_visit(
    place: dict[str, Any],
    day: str,
    earliest_start: int,
    duration: int,
    day_end: int,
) -> tuple[int, str] | None:
    """
    Find the earliest feasible visit.
    Returns (start_minutes, confidence), or None.
    """
    hours = place["hours"]
    confidence = hours["confidence"]

    if confidence != "known":
        if earliest_start + duration <= day_end:
            return earliest_start, confidence
        return None

    weekday = date.fromisoformat(day).strftime("%a").lower()
    intervals = hours.get(weekday)

    if not intervals:
        return None

    for opening, closing in intervals:
        start = max(earliest_start, to_minutes(opening))
        end = min(day_end, to_minutes(closing))

        if start + duration <= end:
            return start, confidence

    return None


def budget_allows(
    remaining: float,
    amount: float,
) -> bool:
    return amount <= remaining + 1e-9


def max_stops(pace: float) -> int:
    """Relaxed travelers visit fewer places."""
    pace = max(0.0, min(1.0, pace))
    return 2 + round(pace * 4)


# Some places only make sense at certain times of day. A place whose categories are ALL
# listed here may only START a visit inside one of its windows (a bar is not a 10 am stop).
# A place with any other category (a market, a neighbourhood with bars) is not limited.
TIME_WINDOWS = {
    "restaurant": [("12:00", "14:30"), ("19:00", "21:30")],
    "bar": [("18:00", "23:59")],
    "nightclub": [("21:00", "23:59")],
}

# Minutes of breathing room after each stop for a fully relaxed traveler (pace 0).
MAX_REST_MINUTES = 30


def time_windows(place: dict[str, Any]) -> list[tuple[int, int]] | None:
    """Allowed start windows in minutes, or None when the place fits any time of day."""
    categories = place.get("categories", [])
    if not categories or any(c not in TIME_WINDOWS for c in categories):
        return None
    windows = sorted({w for c in categories for w in TIME_WINDOWS[c]})
    return [(to_minutes(a), to_minutes(b)) for a, b in windows]


def visit_in_windows(
    place: dict[str, Any],
    day: str,
    earliest_start: int,
    duration: int,
    day_end: int,
) -> tuple[int, str] | None:
    """Like available_visit, but also respects the place's time-of-day windows."""
    windows = time_windows(place)
    if windows is None:
        return available_visit(place, day, earliest_start, duration, day_end)

    for window_open, window_close in windows:
        if earliest_start > window_close:
            continue
        visit = available_visit(
            place, day, max(earliest_start, window_open), duration, day_end
        )
        if visit is not None and visit[0] <= window_close:
            return visit
    return None


def rest_minutes(pace: float) -> int:
    """A relaxed traveler gets more breathing room after each stop; a packed one none."""
    pace = max(0.0, min(1.0, pace))
    return round(MAX_REST_MINUTES * (1.0 - pace))
