"""FastAPI service — the orchestrator.

Endpoints:
    POST /plan                      profile + destination + dates -> Itinerary (saved as a trip)
    GET  /trips/{trip_id}           the trip's current Itinerary
    POST /trips/{trip_id}/feedback  record accepted/rejected places, re-plan, return the Itinerary

Every incoming profile and every outgoing itinerary is validated against the contracts,
so the moment any component drifts from the agreed shapes, we find out here.

This is the seam the Optimizer team plugs into: swap `plan_itinerary` for the
real `/optimizer` schedule() and nothing else in the system needs to change.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.contracts import validate
from api.scheduler_stub import plan_itinerary
from api.trips import TripStore

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


def _build_itinerary(request: dict[str, Any], trip_id: str | None = None) -> dict[str, Any]:
    itinerary = plan_itinerary(
        request["profile"],
        request["destination"],
        request["start_date"],
        request["end_date"],
        trip_id=trip_id,
    )
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

    Rejected places are left out of the new plan. Accepted places are only recorded for
    now; the stub scheduler doesn't use them.
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

    # TODO(optimizer): waiting for re-optimization of only the affected days, keeping the
    # rest of the trip as it was. Until then the whole trip is re-planned from scratch.
    itinerary = _build_itinerary(request, trip_id=trip_id)
    store.save(trip_id, request, itinerary)
    return itinerary
