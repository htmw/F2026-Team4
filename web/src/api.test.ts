import { describe, expect, it } from "vitest";

import { readableError } from "./api";

function detail(body: unknown): string {
  return JSON.stringify({ detail: body });
}

describe("readableError", () => {
  it("shows destination errors", () => {
    const err = readableError("Plan", 422, detail({ destination_errors: ["'japan' is a country, not a city"] }));
    expect(err.message).toBe("'japan' is a country, not a city");
  });

  it("shows request and profile errors too", () => {
    const err = readableError(
      "Plan",
      422,
      detail({ request_errors: ["End date is before start date."], profile_errors: ["Pace must be 0 to 1."] }),
    );
    expect(err.message).toBe("End date is before start date. Pace must be 0 to 1.");
  });

  it("shows a plain string detail", () => {
    expect(readableError("Plan", 503, detail("OpenStreetMap is unreachable")).message).toBe(
      "OpenStreetMap is unreachable",
    );
  });

  it("falls back to the status when the body is empty", () => {
    expect(readableError("Plan", 500, "").message).toBe("Plan request failed (500)");
  });
});
