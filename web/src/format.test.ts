import { describe, expect, it } from "vitest";

import {
  confidenceLabel,
  formatDateRange,
  formatDay,
  formatMoney,
  formatTime,
  openHoursLabel,
  prettifyPlaceId,
  priceLabel,
} from "./format";

describe("format helpers", () => {
  it("labels confidence for the user", () => {
    expect(confidenceLabel("known")).toBe("verified");
    expect(confidenceLabel("inferred")).toBe("estimated");
    expect(confidenceLabel("unknown")).toBe("unverified");
  });

  it("formats an amount with its currency", () => {
    expect(formatMoney(5, "EUR")).toContain("5");
  });

  it("says free, estimated or unknown instead of a bare zero", () => {
    expect(priceLabel(0, "INR", "inferred")).toBe("Free");
    expect(priceLabel(0, "EUR", "known")).toBe("Free");
    expect(priceLabel(700, "INR", "inferred")).toMatch(/^≈ .*700/);
    expect(priceLabel(0, "NPR", "unknown")).toBe("Price unknown");
    expect(priceLabel(15, "EUR", "known")).toContain("15");
    expect(priceLabel(0, "EUR")).toContain("0");
  });

  it("prettifies a fixture place id", () => {
    expect(prettifyPlaceId("fixture:cervejaria-ramiro")).toBe("Cervejaria Ramiro");
  });

  // Exact punctuation ("Thu, 1 Oct" vs "Thu 1 Oct") differs between ICU versions,
  // so these check the parts rather than the whole string.
  it("shows a day as weekday, day and month", () => {
    expect(formatDay("2026-10-01", "en-GB")).toMatch(/^Thu,? 1 Oct$/);
  });

  it("keeps the calendar date in any time zone", () => {
    // Parsed as UTC, so 1 January never turns into 31 December.
    expect(formatDay("2027-01-01", "en-GB")).toMatch(/^Fri,? 1 Jan$/);
  });

  it("returns anything that is not a date unchanged", () => {
    expect(formatDay("not a date", "en-GB")).toBe("not a date");
  });

  it("shows a date range with the year", () => {
    const range = formatDateRange("2026-12-10", "2026-12-12", "en-GB");
    expect(range).toMatch(/^Thu,? 10 Dec – /);
    expect(range).toMatch(/Sat,? 12 Dec 2026$/);
    expect(formatDateRange("2026-12-10", "2026-12-10", "en-GB")).toMatch(/^Thu,? 10 Dec 2026$/);
    expect(formatDateRange("2026-12-30", "2027-01-02", "en-GB")).toMatch(/2026 – .*2027$/);
    expect(formatDateRange("2026-12-10", "2026-12-12", "en-US")).toMatch(/^Thu, Dec 10 – Sat, Dec 12,? 2026$/);
  });
});

describe("formatTime", () => {
  it("shows a 24-hour time as AM or PM", () => {
    expect(formatTime("09:30")).toBe("9:30 AM");
    expect(formatTime("13:05")).toBe("1:05 PM");
    expect(formatTime("12:00")).toBe("12:00 PM");
    expect(formatTime("00:00")).toBe("12:00 AM");
    expect(formatTime("23:59")).toBe("11:59 PM");
  });

  it("leaves anything else alone", () => {
    expect(formatTime("soon")).toBe("soon");
  });
});

describe("openHoursLabel", () => {
  it("says when a place opens and closes", () => {
    expect(openHoursLabel([["10:00", "17:00"]])).toBe("Open 10:00 AM – 5:00 PM");
    expect(openHoursLabel([["12:00", "15:00"], ["19:00", "23:00"]])).toBe(
      "Open 12:00 PM – 3:00 PM and 7:00 PM – 11:00 PM",
    );
    expect(openHoursLabel([["00:00", "23:59"]])).toBe("Open 24 hours");
    expect(openHoursLabel([["12:00", "23:59"]])).toBe("Open 12:00 PM – midnight");
    expect(openHoursLabel(undefined)).toBe("");
  });
});
