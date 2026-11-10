// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

import { ItineraryView } from "./ItineraryView";
import type { Itinerary, PlanRequest } from "./types";

afterEach(cleanup);

const itinerary: Itinerary = {
  trip_id: "trip-1",
  destination: { name: "Tokyo", lat: 35.6, lon: 139.7 },
  start_date: "2030-05-01",
  end_date: "2030-05-01",
  days: [
    {
      date: "2030-05-01",
      items: [
        { place_id: "p1", name: "Sensō-ji", start: "09:30", end: "11:00", cost: 0, reason: "History.", confidence: "known" },
        {
          place_id: "p2",
          name: "Tsukiji Outer Market",
          start: "11:30",
          end: "12:30",
          cost: 3000,
          reason: "Food.",
          confidence: "inferred",
          travel_from_prev: { minutes: 25, mode: "walk" },
        },
      ],
    },
  ],
  totals: { cost: 14000, currency: "JPY", walking_minutes: 25 },
  score: 0.78,
};

function request(budget: { total: number; currency: string }): PlanRequest {
  return {
    destination: { name: "Tokyo, Japan" },
    start_date: "2030-05-01",
    end_date: "2030-05-01",
    profile: {
      interests: {},
      pace: 0.5,
      max_walk_minutes: 20,
      day_start: "09:30",
      day_end: "22:00",
      budget,
      dietary: [],
      accessibility: [],
      avoid: [],
      novelty_appetite: 0.3,
      feedback: { accepted: [], rejected: [] },
    },
  };
}

function renderPlan(req: PlanRequest | null, extra: Partial<Parameters<typeof ItineraryView>[0]> = {}) {
  render(
    <ItineraryView
      itinerary={itinerary}
      request={req}
      rejected={[]}
      onToggleReject={() => {}}
      onReplan={() => {}}
      replanning={false}
      lastRemoved={null}
      onUndo={() => {}}
      undoing={false}
      {...extra}
    />,
  );
}

describe("ItineraryView", () => {
  it("compares the total with the traveler's budget", () => {
    renderPlan(request({ total: 120000, currency: "JPY" }));
    expect(screen.getByText(/of your ¥120,000 budget/)).toBeTruthy();
  });

  it("says when the plan goes over budget", () => {
    renderPlan(request({ total: 10000, currency: "JPY" }));
    expect(screen.getByText(/¥4,000 over your ¥10,000 budget/)).toBeTruthy();
  });

  it("says when the budget could not be applied because of the currency", () => {
    renderPlan(request({ total: 1200, currency: "EUR" }));
    expect(screen.getByText(/Budget in EUR not applied: prices here are in JPY/)).toBeTruthy();
  });

  it("labels every stop's opening-hours confidence, including verified ones", () => {
    renderPlan(null);
    const stops = within(screen.getByRole("region", { name: /Day 1/ }));
    expect(stops.getByText("Hours verified")).toBeTruthy();
    expect(stops.getByText("Hours estimated")).toBeTruthy();
  });

  it("says how far a walk goes over the traveler's limit, and flags that walk", () => {
    renderPlan(request({ total: 120000, currency: "JPY" }));
    expect(screen.getByText(/longest walk 25 min, 5 min over your 20-min limit/)).toBeTruthy();
    expect(screen.getByText(/25 min walk from the previous stop, 5 min over your 20-min limit/)).toBeTruthy();
  });

  it("shows each day's stops, walking and cost", () => {
    renderPlan(null);
    expect(screen.getByText("2 stops · 25 min walking · ¥3,000")).toBeTruthy();
  });

  it("shows a failed re-plan next to the Re-plan button", () => {
    renderPlan(null, { rejected: ["p1"], replanError: "Couldn't re-plan the trip: Planner is restarting. Your plan hasn't changed." });
    expect(screen.getByRole("alert").textContent).toContain("Couldn't re-plan the trip");
    expect(screen.getByRole("button", { name: "Re-plan trip" })).toBeTruthy();
  });

  it("offers Undo after a re-plan removed places", () => {
    const onUndo = vi.fn();
    renderPlan(null, { lastRemoved: [{ id: "p9", name: "Harajuku" }], onUndo });
    expect(screen.getByRole("status").textContent).toContain("Removed Harajuku and re-planned the trip.");
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(onUndo).toHaveBeenCalledTimes(1);
  });
});
