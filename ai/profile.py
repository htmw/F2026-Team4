"""Free text -> TravelerProfile.

The model only reports preferences the traveler stated or clearly implied. It returns a
small, flat JSON object (MODEL_SCHEMA); this module turns that into a TravelerProfile,
fills anything the traveler didn't mention with the preference form's starting values,
and validates the result against the contract. When the reply is invalid, the problems
are sent back to the model and it gets another try.

The model never plans anything. Its output is a profile the traveler can review and edit.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from ai.llm import LLM
from api.contracts import load_categories, validate

MAX_ATTEMPTS = 3

# Same starting values as the preference form (web/src/PreferenceForm.tsx), so a profile
# built from text and one built from the form agree on anything the traveler didn't say.
DEFAULT_PACE = 0.4
DEFAULT_MAX_WALK_MINUTES = 20
DEFAULT_DAY_START = "09:30"
DEFAULT_DAY_END = "22:00"
DEFAULT_BUDGET_TOTAL = 1200
DEFAULT_BUDGET_CURRENCY = "EUR"

_CURRENCY_SYMBOLS = {"€": "EUR", "£": "GBP"}  # "$" and "¥" are ambiguous: left for the model
_SHORT_TIME = re.compile(r"^(\d):(\d\d)$")


class ProfileExtractionError(RuntimeError):
    """The model didn't produce a valid profile within MAX_ATTEMPTS."""

    def __init__(self, errors: list[str], attempts: int):
        super().__init__(f"No valid profile after {attempts} attempts: {'; '.join(errors)}")
        self.errors = errors
        self.attempts = attempts


@dataclass
class ExtractionResult:
    profile: dict[str, Any]
    defaults_used: list[str] = field(default_factory=list)  # fields the traveler didn't mention
    attempts: int = 1


@cache
def _vocabulary() -> tuple[tuple[str, ...], tuple[str, ...]]:
    vocab = load_categories()
    return tuple(vocab["interests"]), tuple(vocab["categories"])


def model_schema() -> dict[str, Any]:
    """The JSON the model must reply with. Every key is required; null means "not mentioned"."""
    interests, categories = _vocabulary()
    properties: dict[str, Any] = {
        "interests": {
            "type": "object",
            "properties": {name: {"type": "number"} for name in interests},
            "required": list(interests),
            "additionalProperties": False,
        },
        "pace": {"type": ["number", "null"]},
        "max_walk_minutes": {"type": ["integer", "null"]},
        "day_start": {"type": ["string", "null"]},
        "day_end": {"type": ["string", "null"]},
        "budget_total": {"type": ["number", "null"]},
        "budget_currency": {"type": ["string", "null"]},
        "dietary": {"type": "array", "items": {"type": "string"}},
        "accessibility": {"type": "array", "items": {"type": "string"}},
        "avoid": {"type": "array", "items": {"type": "string", "enum": list(categories)}},
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _example_reply() -> str:
    """The worked example in the prompt: unmentioned interests at 0.5, unmentioned fields null."""
    interests, _ = _vocabulary()
    weights = {name: 0.5 for name in interests}
    weights.update({"art": 0.9, "history": 0.8, "nightlife": 0.2})
    example = {
        "interests": weights,
        "pace": None,
        "max_walk_minutes": None,
        "day_start": None,
        "day_end": None,
        "budget_total": 1000,
        "budget_currency": "EUR",
        "dietary": [],
        "accessibility": [],
        "avoid": [],
    }
    return json.dumps(example)


def system_prompt() -> str:
    interests, categories = _vocabulary()
    return f"""You turn a traveler's description of their trip into JSON preferences for a \
trip planner. Report only what the traveler said or clearly implied. Do not plan the trip.
When in doubt, use null or 0.5: a missing preference is better than a made-up one.

Fields:
- interests: a weight from 0 to 1 for each of {", ".join(interests)}.
  1 = a main reason for the trip, 0.7 = likes it, 0.2 = not interested,
  0 = actively dislikes it. Use exactly 0.5 for every interest they don't mention.
- pace: 0 to 1. 0.2 = relaxed, few stops a day. 0.5 = balanced. 0.8 = packed, see as much
  as possible. null unless they say how busy or relaxed they want their days.
- max_walk_minutes: the longest walk they accept between two stops, in whole minutes.
  Trouble walking or hating walks means 10 or less; loving long walks means 30 or more.
  null if not mentioned.
- day_start, day_end: 24-hour "HH:MM" times when their day starts and ends. A late riser
  starts around "10:30"; early to bed ends around "20:00". null if not mentioned.
- budget_total: the total budget for the whole trip as a number. null if not mentioned.
- budget_currency: a 3-letter ISO code such as EUR, USD or GBP. null if not mentioned.
- dietary: only diet needs the traveler states, in lowercase, such as "vegan" or
  "gluten-free". [] if they state none. Never assume a diet.
- accessibility: only access needs the traveler states, in lowercase, such as
  "wheelchair" or "limited walking". [] if they state none.
- avoid: kinds of places they say they want to skip, using only these names: \
{", ".join(categories)}. [] if none.

Example. Traveler: "Two of us on a city break. We love museums and aren't big on \
nightlife. About 1000 euros."
Reply: {_example_reply()}

Reply with the JSON object only."""


def _normalize(reply: dict[str, Any]) -> dict[str, Any]:
    """Mechanical clean-ups only (case, padding, whole numbers). Nothing is guessed here."""
    out = dict(reply)
    for key in ("day_start", "day_end"):
        value = out.get(key)
        if isinstance(value, str):
            value = value.strip()
            short = _SHORT_TIME.match(value)
            out[key] = f"0{short.group(1)}:{short.group(2)}" if short else value
    currency = out.get("budget_currency")
    if isinstance(currency, str):
        currency = currency.strip()
        out["budget_currency"] = _CURRENCY_SYMBOLS.get(currency, currency.upper())
    walk = out.get("max_walk_minutes")
    if isinstance(walk, float) and walk.is_integer():
        out["max_walk_minutes"] = int(walk)
    for key in ("dietary", "accessibility"):
        items = out.get(key)
        if isinstance(items, list):
            cleaned = [s.strip().lower() for s in items if isinstance(s, str) and s.strip()]
            out[key] = list(dict.fromkeys(cleaned))
    return out


def _to_profile(reply: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Map the model's flat reply onto the TravelerProfile shape, filling unstated fields."""
    defaults_used: list[str] = []

    def pick(key: str, default: Any) -> Any:
        value = reply.get(key)
        if value is None:
            defaults_used.append(key)
            return default
        return value

    profile: dict[str, Any] = {
        "interests": reply.get("interests"),
        "pace": pick("pace", DEFAULT_PACE),
        "max_walk_minutes": pick("max_walk_minutes", DEFAULT_MAX_WALK_MINUTES),
        "day_start": pick("day_start", DEFAULT_DAY_START),
        "day_end": pick("day_end", DEFAULT_DAY_END),
    }
    total, currency = reply.get("budget_total"), reply.get("budget_currency")
    if total is None:
        defaults_used.append("budget.total")
        total = DEFAULT_BUDGET_TOTAL
    if currency is None:
        defaults_used.append("budget.currency")
        currency = DEFAULT_BUDGET_CURRENCY
    profile["budget"] = {"total": total, "currency": currency}
    for key in ("dietary", "accessibility", "avoid"):
        profile[key] = reply.get(key) or []
    return profile, defaults_used


def _problems(reply: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    """Everything wrong with a reply, phrased so the model can fix it."""
    interests, categories = _vocabulary()
    problems: list[str] = []
    given = reply.get("interests")
    if not isinstance(given, dict):
        problems.append(f"interests must be an object with a weight for each of {list(interests)}.")
    else:
        unknown = sorted(set(given) - set(interests))
        missing = sorted(set(interests) - set(given))
        if unknown:
            problems.append(f"interests has unknown names {unknown}; use only {list(interests)}.")
        if missing:
            problems.append(f"interests is missing {missing}; use 0.5 when not mentioned.")
    avoid = reply.get("avoid") or []
    if not isinstance(avoid, list):
        problems.append("avoid must be a list.")
    elif bad_avoid := sorted(set(avoid) - set(categories)):
        problems.append(f"avoid has unknown names {bad_avoid}; use only {list(categories)}.")
    if not problems:
        problems += [f"{e}." for e in validate("traveler-profile", profile)]
        if not problems and profile["day_end"] <= profile["day_start"]:
            problems.append("day_end must be later than day_start.")
    return problems


def extract_profile(text: str, llm: LLM, *, max_attempts: int = MAX_ATTEMPTS) -> ExtractionResult:
    """Turn a free-text trip description into a contract-valid TravelerProfile.

    Raises ProfileExtractionError if the model can't produce a valid one in `max_attempts`
    tries, and lets ai.llm.LLMError / LLMUnavailable through when the model can't be used.
    """
    messages = [
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": text.strip()},
    ]
    schema = model_schema()
    problems: list[str] = []
    for attempt in range(1, max_attempts + 1):
        raw = llm.chat(messages, schema=schema)
        try:
            parsed = json.loads(raw)
        except ValueError:
            problems = ["The reply was not valid JSON."]
        else:
            if not isinstance(parsed, dict):
                problems = ["The reply must be a JSON object."]
            else:
                reply = _normalize(parsed)
                profile, defaults_used = _to_profile(reply)
                problems = _problems(reply, profile)
                if not problems:
                    return ExtractionResult(profile, defaults_used, attempt)
        messages += [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": "That JSON has problems:\n- "
                + "\n- ".join(problems)
                + "\nReply with the corrected JSON object only.",
            },
        ]
    raise ProfileExtractionError(problems, max_attempts)
