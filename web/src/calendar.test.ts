import { describe, expect, it } from "vitest";

import { icsFileName, itineraryToIcs } from "./calendar";
import type { Itinerary } from "./types";

const itinerary: Itinerary = {
  trip_id: "trip-1",
  destination: { name: "Rome, Italy", lat: 41.9, lon: 12.5 },
  start_date: "2026-12-10",
  end_date: "2026-12-10",
  days: [
    {
      date: "2026-12-10",
      items: [
        {
          place_id: "osm:node/1",
          name: "Campo de' Fiori; market, square",
          start: "09:30",
          end: "10:00",
          cost: 0,
          reason: "Matches your interests in food, history and architecture.",
          confidence: "known",
          description: "A busy market square in central Rome where vendors sell fresh produce, flowers and spices every morning except Sunday.",
        },
      ],
    },
  ],
  totals: { cost: 0, currency: "EUR", walking_minutes: 0 },
};

describe("calendar export", () => {
  const ics = itineraryToIcs(itinerary, new Date("2026-11-17T12:00:00Z"));

  it("writes one event per stop at the local (floating) time", () => {
    expect(ics.startsWith("BEGIN:VCALENDAR\r\n")).toBe(true);
    expect(ics.trimEnd().endsWith("END:VCALENDAR")).toBe(true);
    expect(ics.match(/BEGIN:VEVENT/g)).toHaveLength(1);
    expect(ics).toContain("DTSTART:20261210T093000\r\n");
    expect(ics).toContain("DTEND:20261210T100000\r\n");
    expect(ics).toContain("DTSTAMP:20261117T120000Z");
  });

  it("escapes commas and semicolons in text", () => {
    expect(ics).toContain("SUMMARY:Campo de' Fiori\\; market\\, square");
  });

  it("uses CRLF and folds long lines to 75 octets", () => {
    expect(ics.includes("\n") && !/[^\r]\n/.test(ics)).toBe(true);
    for (const line of ics.split("\r\n")) expect(new TextEncoder().encode(line).length).toBeLessThanOrEqual(75);
    expect(ics).toContain("\r\n "); // the long description was folded
  });

  it("names the file after the city and start date", () => {
    expect(icsFileName(itinerary)).toBe("wanderwise-rome-italy-2026-12-10.ics");
  });
});
