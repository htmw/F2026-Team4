import { describe, expect, it } from "vitest";

import { parseRoute, routeHash } from "./route";
import { shareLink } from "./links";

describe("routes", () => {
  it("reads each page from the URL hash", () => {
    expect(parseRoute("")).toEqual({ page: "plan" });
    expect(parseRoute("#/")).toEqual({ page: "plan" });
    expect(parseRoute("#/login")).toEqual({ page: "login", next: null });
    expect(parseRoute("#/login?next=save")).toEqual({ page: "login", next: "save" });
    expect(parseRoute("#/trips")).toEqual({ page: "trips" });
    expect(parseRoute("#/trip/abc-123")).toEqual({ page: "shared", tripId: "abc-123" });
    expect(parseRoute("#/nowhere")).toEqual({ page: "plan" });
  });

  it("round-trips every route", () => {
    for (const hash of ["#/", "#/login", "#/login?next=save", "#/trips", "#/trip/a%2Fb"]) {
      expect(routeHash(parseRoute(hash))).toBe(hash);
    }
  });

  it("builds a share link to the read-only trip page", () => {
    expect(shareLink("t 1", { origin: "https://wanderwise.app", pathname: "/" })).toBe(
      "https://wanderwise.app/#/trip/t%201",
    );
  });

  it("doesn't break on a malformed trip id", () => {
    expect(parseRoute("#/trip/%E0%A4%A")).toEqual({ page: "shared", tripId: "%E0%A4%A" });
  });
});
