import { describe, expect, it } from "vitest";

import { confidenceLabel, formatMoney, prettifyPlaceId } from "./format";

describe("format helpers", () => {
  it("labels confidence for the user", () => {
    expect(confidenceLabel("known")).toBe("verified");
    expect(confidenceLabel("inferred")).toBe("estimated");
    expect(confidenceLabel("unknown")).toBe("unverified");
  });

  it("formats an amount with its currency", () => {
    expect(formatMoney(5, "EUR")).toContain("5");
  });

  it("prettifies a fixture place id", () => {
    expect(prettifyPlaceId("fixture:cervejaria-ramiro")).toBe("Cervejaria Ramiro");
  });
});
