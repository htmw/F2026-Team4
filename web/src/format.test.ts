import { describe, expect, it } from "vitest";

import { confidenceLabel, formatMoney, prettifyPlaceId, priceLabel } from "./format";

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
});
