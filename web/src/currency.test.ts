import { describe, expect, it } from "vitest";

import { currencyForCountry, currencyOptions } from "./currency";

describe("currency helpers", () => {
  it("picks the local currency for a country code", () => {
    expect(currencyForCountry("JP")).toBe("JPY");
    expect(currencyForCountry("in")).toBe("INR");
    expect(currencyForCountry("PT")).toBe("EUR");
  });

  it("returns undefined for an unknown or missing country", () => {
    expect(currencyForCountry("ZZ")).toBeUndefined();
    expect(currencyForCountry(undefined)).toBeUndefined();
  });

  it("adds an uncommon currency to the dropdown options", () => {
    expect(currencyOptions("GEL")[0]).toBe("GEL");
    expect(currencyOptions("EUR").filter((code) => code === "EUR")).toHaveLength(1);
  });
});
