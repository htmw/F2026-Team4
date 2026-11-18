// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { getSuggestions, SuggestionsUnavailable } from "./api";
import type { Suggestion } from "./api";
import { ItineraryView } from "./ItineraryView";
import { StopSuggestions } from "./StopSuggestions";
import type { Itinerary } from "./types";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ideas: Suggestion[] = [
  { place_id: "trevi", name: "Trevi Fountain", reason: "Matches your interest in architecture.", cost: 0, cost_confidence: "known" },
  { place_id: "borghese", name: "Galleria Borghese", reason: "Matches your interest in art.", cost: 15, cost_confidence: "inferred" },
];

const base = { tripId: "t1", currency: "EUR", date: "2030-05-01", dayNumber: 1, onClose: () => {} };

describe("StopSuggestions", () => {
  it("lists places to swap in and re-plans with the chosen one", async () => {
    const load = vi.fn(async () => ideas);
    const onChoose = vi.fn(async () => {});
    render(<StopSuggestions {...base} replace={{ id: "pantheon", name: "Pantheon" }} onChoose={onChoose} load={load} />);
    expect(screen.getByRole("heading", { name: "Instead of Pantheon" })).toBeTruthy();
    expect(load).toHaveBeenCalledWith("t1", { replace: "pantheon", date: "2030-05-01" });
    expect(await screen.findByText("Trevi Fountain")).toBeTruthy();
    expect(screen.getAllByText(/Matches your interest: art/)[0].closest("p")?.textContent).toBe("Matches your interest: art · ≈ €15.00");
    fireEvent.click(screen.getByRole("button", { name: "Use Galleria Borghese instead of Pantheon" }));
    await waitFor(() => expect(onChoose).toHaveBeenCalledWith(ideas[1]));
  });

  it("says plainly when the planner can't suggest places yet", async () => {
    render(<StopSuggestions {...base} onChoose={async () => {}} load={async () => Promise.reject(new SuggestionsUnavailable())} />);
    expect((await screen.findByRole("status")).textContent).toMatch(/isn't available yet.*remove the stop and re-plan/);
  });

  it("says when nothing else fits", async () => {
    render(<StopSuggestions {...base} onChoose={async () => {}} load={async () => []} />);
    expect((await screen.findByRole("status")).textContent).toMatch(/Nothing else fits this day/);
  });

  it("keeps the plan and explains when the re-plan fails", async () => {
    render(
      <StopSuggestions
        {...base}
        onChoose={async () => Promise.reject(new Error("Planner is restarting."))}
        load={async () => ideas}
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Add Trevi Fountain to Day 1" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/Planner is restarting\. Your plan hasn't changed\./);
  });
});

describe("getSuggestions", () => {
  it("asks for alternatives to a stop on its day", async () => {
    const fetchMock = vi.fn(async () => Response.json({ suggestions: ideas }));
    vi.stubGlobal("fetch", fetchMock);
    expect(await getSuggestions("t 1", { replace: "osm:node/1", date: "2030-05-01" })).toEqual(ideas);
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toMatch(
      /\/trips\/t%201\/suggestions\?replace=osm%3Anode%2F1&date=2030-05-01$/,
    );
  });

  it("treats a missing endpoint as 'not available yet', but a missing trip as an error", async () => {
    vi.stubGlobal("fetch", async () => new Response('{"detail":"Not Found"}', { status: 404 }));
    await expect(getSuggestions("t1")).rejects.toBeInstanceOf(SuggestionsUnavailable);
    vi.stubGlobal("fetch", async () => new Response(`{"detail":"No trip with id 't1'."}`, { status: 404 }));
    await expect(getSuggestions("t1")).rejects.toThrow("No trip with id 't1'.");
  });
});

describe("Swap and Add in the plan", () => {
  const plan: Itinerary = {
    trip_id: "t1",
    destination: { name: "Rome", lat: 41.9, lon: 12.5 },
    start_date: "2030-05-01",
    end_date: "2030-05-01",
    days: [
      {
        date: "2030-05-01",
        items: [{ place_id: "pantheon", name: "Pantheon", start: "09:30", end: "10:30", cost: 0, reason: "History.", confidence: "known" }],
      },
    ],
    totals: { cost: 0, currency: "EUR", walking_minutes: 0 },
  };
  const noop = () => {};
  const props = {
    itinerary: plan,
    request: null,
    rejected: [],
    onToggleReject: noop,
    onReplan: noop,
    replanning: false,
    lastRemoved: null,
    onUndo: noop,
    undoing: false,
  };

  it("opens the swap list for one stop and sends the chosen change", async () => {
    vi.stubGlobal("fetch", async () => Response.json({ suggestions: ideas }));
    const onChangeStop = vi.fn(async () => {});
    render(<ItineraryView {...props} onChangeStop={onChangeStop} />);
    const swap = screen.getByRole("button", { name: "Swap Pantheon for another place" });
    fireEvent.click(swap);
    expect(swap.getAttribute("aria-expanded")).toBe("true");
    const list = within(screen.getByRole("region", { name: "Instead of Pantheon" }));
    fireEvent.click(await list.findByRole("button", { name: "Use Trevi Fountain instead of Pantheon" }));
    await waitFor(() =>
      expect(onChangeStop).toHaveBeenCalledWith({ add: ideas[0], replace: { id: "pantheon", name: "Pantheon" } }),
    );
  });

  it("adds a place to a day", async () => {
    vi.stubGlobal("fetch", async () => Response.json({ suggestions: ideas }));
    const onChangeStop = vi.fn(async () => {});
    render(<ItineraryView {...props} onChangeStop={onChangeStop} />);
    fireEvent.click(screen.getByRole("button", { name: "Add a place to Day 1" }));
    fireEvent.click(await screen.findByRole("button", { name: "Add Galleria Borghese to Day 1" }));
    await waitFor(() => expect(onChangeStop).toHaveBeenCalledWith({ add: ideas[1] }));
  });

  it("shows what the last change did", () => {
    render(<ItineraryView {...props} onChangeStop={async () => {}} changeNote={{ text: "Swapped Pantheon for Trevi Fountain.", ok: true }} />);
    expect(screen.getByRole("status").textContent).toBe("Swapped Pantheon for Trevi Fountain.");
  });

  it("has no Swap or Add on a read-only shared trip", () => {
    render(<ItineraryView {...props} onChangeStop={async () => {}} readOnly />);
    expect(screen.queryByRole("button", { name: /Swap/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Add a place/ })).toBeNull();
  });
});
