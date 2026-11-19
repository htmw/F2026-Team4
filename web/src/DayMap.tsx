// A map of one day: a numbered pin per stop, in the stop's interest colour, joined in visiting
// order by a dashed line (the order, not the street route).
//
// It needs each itinerary item's lat/lon, which the backend doesn't send yet (see
// web/BACKEND-HANDOFF.md). Until then no stop has coordinates and the map isn't shown.
// Leaflet is loaded only when a map is shown, so it costs nothing before that.

import { useEffect, useRef, useState } from "react";

import { formatTimeRange, interestFromReason, prettifyPlaceId } from "./format";
import type { ItineraryItem } from "./types";

export interface MapPoint {
  number: number;
  name: string;
  lat: number;
  lon: number;
  time: string;
  interest: string;
}

const TILE_URL = import.meta.env.VITE_MAP_TILES ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

/** The day's stops that have coordinates, numbered in visiting order (1 = first stop). */
export function mapPoints(items: ItineraryItem[]): MapPoint[] {
  return items.flatMap((item, i) =>
    isCoordinate(item.lat, 90) && isCoordinate(item.lon, 180)
      ? [
          {
            number: i + 1,
            name: item.name ?? prettifyPlaceId(item.place_id),
            lat: item.lat,
            lon: item.lon,
            time: formatTimeRange(item.start, item.end),
            interest: interestFromReason(item.reason) ?? "other",
          },
        ]
      : [],
  );
}

function isCoordinate(value: unknown, limit: number): value is number {
  return typeof value === "number" && Number.isFinite(value) && Math.abs(value) <= limit;
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

interface Props {
  items: ItineraryItem[];
  dayNumber: number;
}

export function DayMap({ items, dayNumber }: Props) {
  const points = mapPoints(items);
  const containerRef = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  // Re-draw only when the stops themselves change.
  const key = JSON.stringify(points);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || points.length === 0) return;
    let map: import("leaflet").Map | null = null;
    let cancelled = false;

    Promise.all([import("leaflet"), import("leaflet/dist/leaflet.css")])
      .then(([module]) => {
        if (cancelled) return;
        const L = (module as { default?: typeof import("leaflet") }).default ?? (module as typeof import("leaflet"));
        map = L.map(container, { scrollWheelZoom: false, zoomControl: true, attributionControl: true });
        map.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>');
        L.tileLayer(TILE_URL, { maxZoom: 19, attribution: ATTRIBUTION }).addTo(map);

        const latLngs = points.map((p) => L.latLng(p.lat, p.lon));
        if (latLngs.length > 1) {
          L.polyline(latLngs, { className: "day-map-path", weight: 3, dashArray: "2 7", lineCap: "round" }).addTo(map);
        }
        for (const p of points) {
          L.marker([p.lat, p.lon], {
            title: `${p.number}. ${p.name}`,
            alt: `${p.number}. ${p.name}`,
            icon: L.divIcon({
              className: "day-map-marker",
              html: `<span class="day-map-pin pin-${escapeHtml(p.interest)}">${p.number}</span>`,
              iconSize: [28, 28],
              iconAnchor: [14, 14],
            }),
          })
            .bindPopup(`<strong>${escapeHtml(p.name)}</strong><br>${escapeHtml(p.time)}`)
            .addTo(map);
        }
        if (latLngs.length === 1) map.setView(latLngs[0], 16);
        else map.fitBounds(L.latLngBounds(latLngs), { padding: [28, 28], maxZoom: 17 });
      })
      .catch(() => !cancelled && setFailed(true));

    return () => {
      cancelled = true;
      map?.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (points.length === 0) return null;
  const missing = items.length - points.length;

  return (
    <figure className="day-map">
      {failed ? (
        <p className="day-map-failed muted">The map couldn't load. The stops are listed below.</p>
      ) : (
        <div
          ref={containerRef}
          className="day-map-canvas"
          role="region"
          aria-label={`Map of Day ${dayNumber}: ${points.length} ${points.length === 1 ? "stop" : "stops"}, numbered in visiting order`}
        />
      )}
      <figcaption className="day-map-caption">
        Numbers follow the visiting order; the dashed line joins the stops, not the street route.
        {missing > 0 && ` ${missing} ${missing === 1 ? "stop isn't" : "stops aren't"} on the map (no location).`}
      </figcaption>
    </figure>
  );
}
