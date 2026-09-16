"""FastAPI service — the orchestrator.

For now it does one thing: POST /plan takes a traveler profile + destination +
dates and returns a valid Itinerary produced by the stub scheduler. It validates
the incoming profile and the outgoing itinerary against the contracts, so the
moment any component drifts from the agreed shapes, we find out here.

This is the seam the Optimizer team plugs into: swap `plan_itinerary` for the
real `/optimizer` schedule() and nothing else in the system needs to change.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.contracts import validate
from api.scheduler_stub import plan_itinerary

app = FastAPI(title="Travel Recommender API (stub)", version="0.0.1")

# Dev-only: let the Vite frontend (localhost:5173) call us. Tighten before any real deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PlanRequest(BaseModel):
    profile: dict[str, Any]
    destination: dict[str, Any]
    start_date: str
    end_date: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/plan")
def plan(req: PlanRequest) -> dict[str, Any]:
    profile_errors = validate("traveler-profile", req.profile)
    if profile_errors:
        raise HTTPException(status_code=422, detail={"profile_errors": profile_errors})

    itinerary = plan_itinerary(req.profile, req.destination, req.start_date, req.end_date)

    # If our own output breaks the contract, fail loudly — that's a bug, not a bad request.
    itinerary_errors = validate("itinerary", itinerary)
    if itinerary_errors:
        raise HTTPException(status_code=500, detail={"itinerary_errors": itinerary_errors})

    return itinerary
