// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { DescribeTrip } from "./DescribeTrip";
import type { TravelerProfile } from "./types";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const PROFILE: TravelerProfile = {
  interests: { food: 1, history: 1 },
  pace: 0.3,
  max_walk_minutes: 20,
  day_start: "09:30",
  day_end: "22:00",
  budget: { total: 1000, currency: "EUR" },
  dietary: [],
  accessibility: [],
  avoid: [],
  novelty_appetite: 0.3,
  feedback: { accepted: [], rejected: [] },
};

function stubFetch(body: unknown, ok = true, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok,
      status,
      json: async () => body,
      text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
    })),
  );
}

function typeDescription(value: string) {
  fireEvent.change(screen.getByLabelText(/describe your trip/i), { target: { value } });
}

describe("DescribeTrip", () => {
  it("sends the text to /profile/from-text and hands back the profile", async () => {
    stubFetch({ profile: PROFILE, defaults_used: ["budget"] });
    const onProfile = vi.fn();
    render(<DescribeTrip onProfile={onProfile} />);

    typeDescription("I love food and history");
    fireEvent.click(screen.getByRole("button", { name: /fill from description/i }));

    await waitFor(() => expect(onProfile).toHaveBeenCalledWith(PROFILE, ["budget"]));

    const [url, init] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(String(url)).toContain("/profile/from-text");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({
      text: "I love food and history",
    });
  });

  it("shows a friendly message when the assistant is unavailable (503)", async () => {
    stubFetch("The model is not reachable.", false, 503);
    render(<DescribeTrip onProfile={vi.fn()} />);

    typeDescription("anything");
    fireEvent.click(screen.getByRole("button", { name: /fill from description/i }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/isn't available/i);
  });

  it("asks for text when the box is empty and never calls the API", () => {
    stubFetch({});
    const onProfile = vi.fn();
    render(<DescribeTrip onProfile={onProfile} />);

    fireEvent.click(screen.getByRole("button", { name: /fill from description/i }));

    expect(screen.getByRole("alert").textContent).toMatch(/write a sentence/i);
    expect(vi.mocked(globalThis.fetch)).not.toHaveBeenCalled();
    expect(onProfile).not.toHaveBeenCalled();
  });
});
