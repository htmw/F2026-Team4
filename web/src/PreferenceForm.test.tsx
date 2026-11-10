// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

import { PreferenceForm } from "./PreferenceForm";
import type { PlanRequest } from "./types";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderForm(props: Partial<Parameters<typeof PreferenceForm>[0]> = {}) {
  const onSubmit = vi.fn<(req: PlanRequest) => void>();
  render(<PreferenceForm onSubmit={onSubmit} submitting={false} {...props} />);
  return { onSubmit };
}

function currentStep() {
  return screen.getByRole("heading", { level: 3 }).textContent;
}

// Fill step 1 with a typed city and future dates, then go to Preferences.
function completeTripDetails() {
  fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2030-05-01" } });
  fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2030-05-03" } });
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
}

describe("PreferenceForm", () => {
  it("goes from Preferences to Review on Next, without planning the trip", () => {
    // Regression: Next on Preferences used to submit the form and skip Review.
    const { onSubmit } = renderForm();
    completeTripDetails();
    expect(currentStep()).toBe("Preferences");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(currentStep()).toBe("Review");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("moves forward when Enter submits a step", () => {
    renderForm();
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2030-05-01" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2030-05-03" } });
    // Enter in a field submits the form, which advances the wizard.
    fireEvent.submit(screen.getByLabelText("End date").closest("form")!);
    expect(currentStep()).toBe("Preferences");
  });

  it("starts with no dietary needs selected", () => {
    renderForm();
    completeTripDetails();
    fireEvent.click(screen.getByRole("button", { name: /More options/ }));
    const diet = screen.getByRole("group", { name: "Dietary needs" });
    expect(within(diet).getAllByRole("checkbox").filter((box) => (box as HTMLInputElement).checked)).toHaveLength(0);
  });

  it("sends Skip / Some / Love and the pace as the numbers the contract expects", () => {
    const { onSubmit } = renderForm();
    completeTripDetails();
    fireEvent.click(within(screen.getByRole("group", { name: "Nightlife" })).getByLabelText("Love"));
    fireEvent.click(within(screen.getByRole("group", { name: "Food" })).getByLabelText("Skip"));
    fireEvent.click(screen.getByLabelText("Relaxed"));
    fireEvent.click(within(screen.getByRole("group", { name: "Longest walk between stops" })).getByLabelText("10 min"));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Plan my trip" }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const { profile } = onSubmit.mock.calls[0][0];
    expect(profile.interests.nightlife).toBe(1);
    expect(profile.interests.food).toBe(0);
    expect(profile.interests.art).toBe(0.5);
    expect(profile.pace).toBe(0.2);
    expect(profile.max_walk_minutes).toBe(10);
    expect(profile.dietary).toEqual([]);
  });

  it("switches the budget to the city's currency and asks for a new amount", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          features: [{ properties: { name: "Tokyo", country: "Japan", osm_value: "city", countrycode: "JP" } }],
        }),
      })),
    );
    renderForm();
    fireEvent.change(screen.getByRole("combobox", { name: "Destination" }), { target: { value: "Toky" } });
    fireEvent.click(await screen.findByRole("option", { name: "Tokyo, Japan" }));
    completeTripDetails();

    expect(screen.getByLabelText("Budget currency")).toHaveProperty("value", "JPY");
    // 1200 EUR must not silently become ¥1,200.
    expect(screen.getByLabelText("Budget for the whole trip")).toHaveProperty("value", "");
    expect(screen.getByText(/Enter an amount in JPY/)).toBeTruthy();
  });

  it("shows a destination error from the server on the Destination field", () => {
    renderForm({ destinationError: { message: "'japan' is a country, not a city", seq: 1 } });
    const input = screen.getByRole("combobox", { name: "Destination" });
    expect(currentStep()).toBe("Trip details");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByRole("alert").textContent).toBe("'japan' is a country, not a city");
  });
});
