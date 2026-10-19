
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
