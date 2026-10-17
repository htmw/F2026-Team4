
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.contracts import validate

from optimizer.scheduler import plan_itinerary


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

    # Step 2: Generate optimized itinerary
    try:
        itinerary = plan_itinerary(
            profile=req.profile,
            destination=req.destination,
            start_date=req.start_date,
            end_date=req.end_date,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error

    # Step 3: Validate generated itinerary
    itinerary_errors = validate(
        "itinerary",
        itinerary
    )

    if itinerary_errors:
        raise HTTPException(
            status_code=500,
            detail={
                "itinerary_errors": itinerary_errors
            }
        )

    # Step 4: Return optimized travel plan
    return itinerary
