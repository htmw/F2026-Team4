// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { ItineraryView } from "./ItineraryView";
import { SharedTrip } from "./SharedTrip";
import type { Itinerary } from "./types";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const plan: Itinerary = {
  trip_id: "t1",
  destination: { name: "Rome", lat: 41.9, lon: 12.5 },
  start_date: "2030-05-01",
  end_date: "2030-05-01",
  days: [
    {
      date: "2030-05-01",
      items: [{ place_id: "p1", name: "Pantheon", start: "09:30", end: "10:30", cost: 0, reason: "History.", confidence: "known" }],
    },
  ],
  totals: { cost: 0, currency: "EUR", walking_minutes: 0 },
};

const noop = () => {};

describe("SharedTrip", () => {
  it("shows the trip read only: no Remove, no Save", async () => {
    render(<SharedTrip tripId="t1" load={async () => plan} />);
    expect(await screen.findByRole("heading", { name: "Pantheon" })).toBeTruthy();
    expect(screen.getByText(/read-only copy/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Remove Pantheon/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Save trip" })).toBeNull();
    // Export still works for whoever opens the link.
    expect(screen.getByRole("button", { name: /Add to calendar/ })).toBeTruthy();
  });

  it("says when the trip can't be found", async () => {
    render(
      <SharedTrip
        tripId="gone"
        load={async () => {
          throw new Error("This trip couldn't be found.");
        }}
      />,
    );
    expect((await screen.findByRole("alert")).textContent).toContain("This trip couldn't be found.");
  });
});

describe("Share button", () => {
  function renderWithShare() {
    render(
      <ItineraryView
        itinerary={plan}
        request={null}
        rejected={[]}
        onToggleReject={noop}
        onReplan={noop}
        replanning={false}
        lastRemoved={null}
        onUndo={noop}
        undoing={false}
        shareUrl="http://localhost/#/trip/t1"
      />,
    );
  }

  it("copies the read-only link", async () => {
    const writeText = vi.fn(async () => {});
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    renderWithShare();
    fireEvent.click(screen.getByRole("button", { name: "Share" }));
    expect(await screen.findByRole("button", { name: "Link copied" })).toBeTruthy();
    expect(writeText).toHaveBeenCalledWith("http://localhost/#/trip/t1");
  });

  it("shows the link to copy by hand when the browser won't copy", async () => {
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText: async () => Promise.reject(new Error("denied")) } });
    renderWithShare();
    fireEvent.click(screen.getByRole("button", { name: "Share" }));
    const input = (await screen.findByLabelText(/Copy this link/)) as HTMLInputElement;
    expect(input.value).toBe("http://localhost/#/trip/t1");
  });
});
