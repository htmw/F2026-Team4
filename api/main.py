"""FastAPI service — the orchestrator.

Endpoints:
    POST /plan                      profile + destination + dates -> Itinerary (saved as a trip)
    GET  /trips/{trip_id}           the trip's current Itinerary
    POST /trips/{trip_id}/feedback  record accepted/rejected places, re-plan, return the Itinerary
    GET  /trips/{trip_id}/suggestions  up to 5 places to swap in for a stop or add to a day
    POST /profile/from-text         free-text trip description -> TravelerProfile (via /ai)

Every incoming profile and every outgoing itinerary is validated against the contracts,
so the moment any component drifts from the agreed shapes, we find out here.

Planning goes through `optimizer.scheduler.plan_itinerary`, which respects opening
hours, travel time, budget and walking limits. `api/scheduler_stub.py` is kept as the
original baseline.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai import LLM, LLMError, LLMUnavailable, ProfileExtractionError, extract_profile, get_llm
from api.contracts import validate
from api.trips import TripStore
from ingest.catalog import CityFetchFailed, CityNotAvailable
from optimizer.scheduler import plan_itinerary
from optimizer.suggest import suggest_for_trip

app = FastAPI(
    title="Wanderwise Travel Planning API",
    description=(
        "Personalized travel recommendations with "
        "constraint-aware itinerary optimization."
    ),
    version="1.0.0",
)

# Allow frontend communication during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "wanderwise.db"
store = TripStore(os.environ.get("WANDERWISE_DB", _DEFAULT_DB))


class PlanRequest(BaseModel):
    profile: dict[str, Any]
    destination: dict[str, Any]
    start_date: str
    end_date: str


class Feedback(BaseModel):
    accepted: list[str] = []
    rejected: list[str] = []


class ProfileText(BaseModel):
    text: str


MAX_PROFILE_TEXT = 2000  # characters; a trip description, not an essay


def _request_errors(req: PlanRequest) -> list[str]:
    """Checks the schemas can't express: real dates in order, and a non-empty daily window."""
    errors: list[str] = []
    try:
        start, end = date.fromisoformat(req.start_date), date.fromisoformat(req.end_date)
    except ValueError:
        errors.append("start_date and end_date must be dates in YYYY-MM-DD format.")
    else:
        if end < start:
            errors.append("end_date can't be before start_date.")
    # The profile schema guarantees zero-padded HH:MM, so string comparison is safe here.
    if req.profile["day_end"] <= req.profile["day_start"]:
        errors.append("profile.day_end must be later than profile.day_start.")
    return errors


def _city_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, CityFetchFailed):
        # The city may be fine; OpenStreetMap is down or rate limiting us. Worth a retry.
        return HTTPException(status_code=503, detail={"destination_errors": [str(exc)]})
    # Say so plainly instead of planning a trip in some other city.
    return HTTPException(status_code=422, detail={"destination_errors": [str(exc)]})


def _is_iso_date(text: str) -> bool:
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _build_itinerary(
    request: dict[str, Any],
    trip_id: str | None = None,
    must_visit_on: dict[str, str] | None = None,
) -> dict[str, Any]:
    try:
        itinerary = plan_itinerary(
            request["profile"],
            request["destination"],
            request["start_date"],
            request["end_date"],
            trip_id=trip_id,
            must_visit_on=must_visit_on,
        )
    except CityNotAvailable as exc:  # CityFetchFailed is a CityNotAvailable too
        raise _city_errors(exc) from exc
    # If our own output breaks the contract, fail loudly — that's a bug, not a bad request.
    itinerary_errors = validate("itinerary", itinerary)
    if itinerary_errors:
        raise HTTPException(status_code=500, detail={"itinerary_errors": itinerary_errors})
    return itinerary


def _load_trip(trip_id: str) -> dict[str, Any]:
    trip = store.get(trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail=f"No trip with id {trip_id!r}.")
    return trip


def _merge_feedback(current: dict[str, list[str]], new: Feedback) -> dict[str, list[str]]:
    """Add the new decisions to the profile's feedback. The newest decision on a place wins."""
    accepted = [p for p in current.get("accepted", []) if p not in new.rejected]
    rejected = [p for p in current.get("rejected", []) if p not in new.accepted]
    accepted += [p for p in new.accepted if p not in accepted]
    rejected += [p for p in new.rejected if p not in rejected]
    return {"accepted": accepted, "rejected": rejected}


def _swap_days(itinerary: dict[str, Any], feedback: Feedback) -> dict[str, str]:
    """On a swap (a stop rejected and a place accepted together), the new place should go
    on the day of the stop it replaces: {accepted_place_id: that day}."""
    if not (feedback.accepted and feedback.rejected):
        return {}
    swapped_out = feedback.rejected[0]
    day = next(
        (d["date"] for d in itinerary.get("days", [])
         if any(i["place_id"] == swapped_out for i in d["items"])),
        None,
    )
    return {pid: day for pid in feedback.accepted} if day else {}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/plan")
def plan(req: PlanRequest) -> dict[str, Any]:

    # Step 1: Validate traveler profile
    profile_errors = validate(
        "traveler-profile",
        req.profile
    )

    if profile_errors:
        raise HTTPException(
            status_code=422,
            detail={
                "profile_errors": profile_errors
            }
        )

    request_errors = _request_errors(req)
    if request_errors:
        raise HTTPException(status_code=422, detail={"request_errors": request_errors})

    request = req.model_dump()
    itinerary = _build_itinerary(request)
    store.save(itinerary["trip_id"], request, itinerary)
    return itinerary


@app.get("/trips/{trip_id}")
def get_trip(trip_id: str) -> dict[str, Any]:
    return _load_trip(trip_id)["itinerary"]


@app.post("/trips/{trip_id}/feedback")
def give_feedback(trip_id: str, feedback: Feedback) -> dict[str, Any]:
    """Record accepted/rejected places on the trip's profile, then re-plan the trip.

    Rejected places are left out of the new plan. Accepted places (a swap, an added place,
    an undone removal) are must-visit: the optimizer schedules each one where it fits, and
    on a swap, on the day of the stop it replaces when there is room. One that fits nowhere
    is named in the itinerary's warnings.
    """
    both = set(feedback.accepted) & set(feedback.rejected)
    if both:
        raise HTTPException(
            status_code=422,
            detail=f"A place can't be both accepted and rejected: {sorted(both)}",
        )

    trip = _load_trip(trip_id)
    request = trip["request"]
    profile = request["profile"]
    profile["feedback"] = _merge_feedback(profile.get("feedback", {}), feedback)

    # TODO(optimizer): re-optimize only the affected days, keeping the rest of the trip as
    # it was. Until then the whole trip is re-planned from scratch.
    must_visit_on = _swap_days(trip["itinerary"], feedback)
    itinerary = _build_itinerary(request, trip_id=trip_id, must_visit_on=must_visit_on)
    store.save(trip_id, request, itinerary)
    return itinerary


@app.get("/trips/{trip_id}/suggestions")
def suggestions(
    trip_id: str,
    replace: Annotated[str | None, Query(description="place_id of the stop to swap out")] = None,
    date: Annotated[str | None, Query(description="YYYY-MM-DD day to add a place to")] = None,
) -> dict[str, Any]:
    """Up to 5 places, best first, to swap in for `replace` or add to `date`.

    Ranked like planning (rule score, the trained ranker when a model exists, verified
    hours preferred), then by fit for the moment: open that day, near the replaced stop or
    the day's stops, indoors when rain is likely. Places already in the trip or rejected
    are left out. Choosing one goes through POST /trips/{id}/feedback as usual.
    """
    trip = _load_trip(trip_id)
    if date is not None and not _is_iso_date(date):
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD.")
    try:
        found = suggest_for_trip(trip["request"], trip["itinerary"], replace=replace, day=date)
    except CityNotAvailable as exc:
        raise _city_errors(exc) from exc
    return {"suggestions": found}


@app.post("/profile/from-text")
def profile_from_text(body: ProfileText, llm: Annotated[LLM, Depends(get_llm)]) -> dict[str, Any]:
    """Turn a free-text trip description into a TravelerProfile the form can start from.

    Returns {"profile": TravelerProfile, "defaults_used": [field, ...]}. `defaults_used`
    names the fields the traveler didn't mention, which were filled with the form's
    starting values, so the UI can ask the traveler to check them.
    """
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text must not be empty.")
    if len(text) > MAX_PROFILE_TEXT:
        raise HTTPException(
            status_code=422, detail=f"text must be at most {MAX_PROFILE_TEXT} characters."
        )
    try:
        result = extract_profile(text, llm)
    except LLMUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (LLMError, ProfileExtractionError) as exc:
        # The model answered, but not with a usable profile. Not the client's fault.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"profile": result.profile, "defaults_used": result.defaults_used}
