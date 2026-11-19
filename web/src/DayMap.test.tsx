// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

import { DayMap, mapPoints } from "./DayMap";
import type { ItineraryItem } from "./types";

// Leaflet needs a real browser to draw; here we only check what the map is asked to draw.
const drawn = vi.hoisted(() => ({ markers: [] as string[], lines: 0 }));
vi.mock("leaflet/dist/leaflet.css", () => ({}));
vi.mock("leaflet", () => {
  const chain = () => ({ addTo: () => chain(), bindPopup: () => chain() });
  return {
    default: {
      map: () => ({ setView() {}, fitBounds() {}, remove() {}, attributionControl: { setPrefix() {} } }),
      tileLayer: () => chain(),
      latLng: (lat: number, lon: number) => [lat, lon],
      latLngBounds: (points: unknown) => points,
      polyline: () => {
        drawn.lines += 1;
        return chain();
      },
      marker: (_: unknown, options: { title: string }) => {
        drawn.markers.push(options.title);
        return chain();
      },
      divIcon: () => ({}),
    },
  };
});

afterEach(() => {
  cleanup();
  drawn.markers = [];
  drawn.lines = 0;
});

function stop(name: string, coords?: [number, number]): ItineraryItem {
  return {
    place_id: name,
    name,
    start: "09:30",
    end: "10:30",
    cost: 0,
    reason: "Matches your interest in history.",
    confidence: "known",
    ...(coords ? { lat: coords[0], lon: coords[1] } : {}),
  };
}

describe("mapPoints", () => {
  it("numbers stops in visiting order and skips ones without a location", () => {
    const points = mapPoints([stop("Pantheon", [41.8986, 12.4769]), stop("Somewhere"), stop("Trevi", [41.9009, 12.4833])]);
    expect(points.map((p) => [p.number, p.name])).toEqual([
      [1, "Pantheon"],
      [3, "Trevi"],
    ]);
    expect(points[0]).toMatchObject({ interest: "history", time: "9:30 AM - 10:30 AM" });
  });

  it("ignores impossible coordinates", () => {
    expect(mapPoints([{ ...stop("Bad"), lat: 120, lon: 10 }, { ...stop("NaN"), lat: Number.NaN, lon: 1 }])).toEqual([]);
  });
});

describe("DayMap", () => {
  it("isn't shown until the plan has locations", () => {
    const { container } = render(<DayMap items={[stop("Pantheon"), stop("Trevi")]} dayNumber={1} />);
    expect(container.innerHTML).toBe("");
  });

  it("draws a numbered pin per stop joined in order", async () => {
    render(<DayMap items={[stop("Pantheon", [41.8986, 12.4769]), stop("Trevi", [41.9009, 12.4833])]} dayNumber={2} />);
    expect(screen.getByRole("region", { name: /Map of Day 2: 2 stops/ })).toBeTruthy();
    await waitFor(() => expect(drawn.markers).toEqual(["1. Pantheon", "2. Trevi"]));
    expect(drawn.lines).toBe(1);
  });

  it("says when a stop is missing from the map", () => {
    render(<DayMap items={[stop("Pantheon", [41.8986, 12.4769]), stop("Somewhere")]} dayNumber={1} />);
    expect(screen.getByText(/1 stop isn't on the map/)).toBeTruthy();
  });
});
