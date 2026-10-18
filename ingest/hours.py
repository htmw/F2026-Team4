"""Parse OSM `opening_hours` into the contract's weekly shape.

Deliberately strict: if any part of the string is outside the supported subset, the
whole value is reported `unparseable` rather than half-guessed, so a `known` label
always means the entire string was understood.

Supported: `24/7`; rules separated by `;`; day lists/ranges (Mo-Fr, Mo,We, Sa-Mo);
time ranges (comma separated for split hours); `off`/`closed`; `24:00` closing;
overnight spans (22:00-02:00, split across two days); later rules override earlier
ones for the same day. `PH`/`SH` (holiday) rules are ignored and recorded in
`ignored`, because the contract has no holiday field.
Not supported (-> unparseable): months, week numbers, sunrise/sunset, `+`, `[n]`, comments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_OSM_DAY = {"Mo": 0, "Tu": 1, "We": 2, "Th": 3, "Fr": 4, "Sa": 5, "Su": 6}
_DAY_ITEM = re.compile(r"^(Mo|Tu|We|Th|Fr|Sa|Su)(?:-(Mo|Tu|We|Th|Fr|Sa|Su))?$")
_TIME_RANGE = re.compile(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$")
_HOLIDAY = {"PH", "SH"}


class _Unsupported(Exception):
    pass


@dataclass
class HoursResult:
    hours: dict | None  # contract hours dict (confidence "known") when status == "parsed"
    status: str  # "parsed" | "absent" | "unparseable"
    reason: str | None = None
    ignored: list[str] = field(default_factory=list)


def _fmt(minutes: int) -> str:
    minutes = min(minutes, 1439)  # contract has no 24:00
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _to_min(h: int, m: int) -> int:
    if m > 59 or h > 24 or (h == 24 and m != 0):
        raise _Unsupported(f"invalid time {h}:{m:02d}")
    return h * 60 + m


def _expand_days(item: str) -> list[int]:
    m = _DAY_ITEM.match(item)
    if not m:
        raise _Unsupported(f"unsupported day selector: {item!r}")
    start = _OSM_DAY[m.group(1)]
    end = start if m.group(2) is None else _OSM_DAY[m.group(2)]
    days, d = [start], start
    while d != end:
        d = (d + 1) % 7
        days.append(d)
    return days


def _split_rule(rule: str) -> tuple[str | None, str]:
    rule = re.sub(r",\s+", ",", rule.strip())
    parts = rule.split(None, 1)
    first = parts[0]
    if first[0].isalpha() and first.lower() not in ("off", "closed"):
        if len(parts) == 1:
            raise _Unsupported(f"rule without times: {rule!r}")
        return first, parts[1]
    return None, rule


def _parse_times(rest: str):
    """None for closed, else a list of (start_min, end_min)."""
    low = rest.strip().lower()
    if low in ("off", "closed"):
        return None
    if low == "24/7":
        return [(0, 1440)]
    ranges = []
    for part in rest.split(","):
        m = _TIME_RANGE.match(part.strip())
        if not m:
            raise _Unsupported(f"unsupported time spec: {part.strip()!r}")
        h1, m1, h2, m2 = (int(x) for x in m.groups())
        s, e = _to_min(h1, m1), _to_min(h2, m2)
        if s >= 1440 or s == e:
            raise _Unsupported(f"unsupported time range: {part.strip()!r}")
        ranges.append((s, e))
    return ranges


def _merge(windows: list[tuple[int, int]]):
    if not windows:
        return None
    merged: list[list[int]] = []
    for s, e in sorted(windows):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [[_fmt(s), _fmt(e)] for s, e in merged]


def _parse(text: str):
    own = [[] for _ in range(7)]  # windows starting on this day
    spill = [[] for _ in range(7)]  # overnight tail that runs into the *next* day
    mentioned: set[int] = set()  # days some rule talks about
    ignored: list[str] = []
    rules = [r for r in text.split(";") if r.strip()]
    if not rules:
        raise _Unsupported("empty value")
    for rule in rules:
        days_part, rest = _split_rule(rule)
        if days_part is None:
            days = list(range(7))
        else:
            days = []
            for item in days_part.split(","):
                if item in _HOLIDAY:
                    ignored.append(f"{item}: {rest}")
                else:
                    days.extend(_expand_days(item))
            if not days:  # holiday-only rule
                continue
        parsed = _parse_times(rest)
        mentioned.update(days)
        for d in days:
            own[d], spill[d] = [], []
            for s, e in parsed or []:
                if e > s:
                    own[d].append((s, e))
                else:  # overnight
                    own[d].append((s, 1440))
                    if e > 0:
                        spill[d].append((0, e))

    if not any(own[d] or spill[d] for d in range(7)):
        # Holiday-only rules do not describe normal weekly opening hours.
        if not mentioned:
            raise _Unsupported("no supported weekly hours; only holiday rules found")
        # "Su off" on its own is how mappers write "closed on Sundays". It says nothing
        # about the other days, so it must not become "known closed every day". Only a
        # value that names every day (off, Mo-Su off) really means closed all week.
        if len(mentioned) < 7:
            raise _Unsupported("only closed days are given; the open days are not stated")

    hours = {name: _merge(own[d] + spill[(d - 1) % 7]) for d, name in enumerate(DAYS)}
    hours["confidence"] = "known"
    return hours, ignored


def parse_opening_hours(raw) -> HoursResult:
    if raw is None or not str(raw).strip():
        return HoursResult(None, "absent")
    try:
        hours, ignored = _parse(str(raw).strip())
    except _Unsupported as exc:
        return HoursResult(None, "unparseable", str(exc))
    return HoursResult(hours, "parsed", ignored=ignored)
