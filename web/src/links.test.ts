import { describe, expect, it } from "vitest";

import { dayRouteLink, mapsLink, ticketLink } from "./links";
import type { ItineraryItem } from "./types";

const stop = (overrides: Partial<ItineraryItem> = {}): ItineraryItem => ({
  place_id: "osm:node/1",
  name: "Colosseo",
  start: "09:30",
  end: "11:00",
  cost: 18,
  cost_confidence: "known",
  reason: "Matches your interests in history and architecture.",
  confidence: "known",
  ...overrides,
});

describe("map links", () => {
  it("searches Google Maps for the place in its city", () => {
    expect(mapsLink(stop(), "Rome, Italy")).toBe(
      "https://www.google.com/maps/search/?api=1&query=Colosseo%2C%20Rome%2C%20Italy",
    );
  });

  it("routes a day through its stops in order", () => {
    const url = dayRouteLink([stop(), stop({ name: "Pantheon" }), stop({ name: "Campo de' Fiori" })], "Rome");
    expect(url).toContain("/maps/dir/?api=1");
    expect(url).toContain("origin=Colosseo%2C%20Rome");
    expect(url).toContain("waypoints=Pantheon%2C%20Rome");
    expect(url).toContain("destination=Campo%20de'%20Fiori%2C%20Rome");
  });

  it("has no route for a day with a single stop", () => {
    expect(dayRouteLink([stop()], "Rome")).toBeNull();
  });

  it("keeps at most 9 stops between the start and the end", () => {
    const items = Array.from({ length: 14 }, (_, i) => stop({ name: `Stop ${i}` }));
    const waypoints = decodeURIComponent(dayRouteLink(items, "Rome")!.split("waypoints=")[1]);
    expect(waypoints.split("|")).toHaveLength(9);
  });
});

describe("ticket links", () => {
  const site = { website: "https://colosseo.it" };

  it("offers tickets on the official website for a paid attraction", () => {
    expect(ticketLink(stop(site), "history")).toEqual({ label: "Tickets", href: "https://colosseo.it/" });
  });

  it("offers tickets when the price is unknown (it may charge)", () => {
    expect(ticketLink(stop({ ...site, cost: 0, cost_confidence: "unknown" }), "art")).not.toBeNull();
  });

  it("offers nothing for restaurants", () => {
    expect(ticketLink(stop({ ...site, reason: "Matches your interest in food." }), "food")).toBeNull();
  });

  it("offers nothing for places known to be free", () => {
    expect(ticketLink(stop({ ...site, cost: 0, cost_confidence: "known" }), "nature")).toBeNull();
  });

  it("offers nothing without a website, or with a non-web link", () => {
    expect(ticketLink(stop(), "history")).toBeNull();
    expect(ticketLink(stop({ website: "javascript:alert(1)" }), "history")).toBeNull();
  });
});
