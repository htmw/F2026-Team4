// Outbound links for a stop or a day: Google Maps (opens the Maps app on phones, with photos,
// reviews and directions) and, for a paid tourist attraction whose data has one, its official
// website for tickets. Links only ever go to Google Maps or to the official site recorded in
// OpenStreetMap, never to a ticket reseller.

import type { ItineraryItem } from "./types";

const MAPS_SEARCH = "https://www.google.com/maps/search/?api=1&query=";
const MAPS_DIRECTIONS = "https://www.google.com/maps/dir/?api=1";
// Google Maps directions links take at most 9 stops between the start and the end.
const MAX_WAYPOINTS = 9;

function placeQuery(item: Pick<ItineraryItem, "name" | "place_id">, city: string): string {
  const name = item.name?.trim() || item.place_id;
  return city ? `${name}, ${city}` : name;
}

/** Google Maps search for one stop: "Colosseo, Rome, Italy". */
export function mapsLink(item: Pick<ItineraryItem, "name" | "place_id">, city: string): string {
  return MAPS_SEARCH + encodeURIComponent(placeQuery(item, city));
}

/**
 * Google Maps directions through a day's stops, in order. Null for a day with fewer than two
 * stops. Days with more stops than a directions link can hold keep the first and last stops and
 * the earliest stops in between.
 */
export function dayRouteLink(items: Pick<ItineraryItem, "name" | "place_id">[], city: string): string | null {
  if (items.length < 2) return null;
  const queries = items.map((item) => placeQuery(item, city));
  const origin = queries[0];
  const destination = queries[queries.length - 1];
  const waypoints = queries.slice(1, -1).slice(0, MAX_WAYPOINTS);
  const params = [`origin=${encodeURIComponent(origin)}`, `destination=${encodeURIComponent(destination)}`];
  if (waypoints.length) params.push(`waypoints=${encodeURIComponent(waypoints.join("|"))}`);
  return `${MAPS_DIRECTIONS}&${params.join("&")}`;
}

export interface TicketLink {
  label: "Tickets";
  href: string;
}

/** Only http(s) links are followed; anything else in the data is ignored. */
function safeUrl(raw: string | undefined): string | null {
  if (!raw) return null;
  try {
    const url = new URL(raw.trim());
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

/**
 * "Tickets", linking to the attraction's official website, for a tourist attraction that charges
 * (or whose price is unknown) and whose data has a website. Null for restaurants and food stops,
 * for places known to be free (parks, squares, viewpoints), and when there is no usable website.
 */
export function ticketLink(item: ItineraryItem, interest: string | null): TicketLink | null {
  if (interest === "food") return null;
  const knownFree = item.cost <= 0 && item.cost_confidence !== "unknown";
  if (knownFree) return null;
  const href = safeUrl(item.website);
  return href ? { label: "Tickets", href } : null;
}
