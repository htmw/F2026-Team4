// Export a plan as an iCalendar (.ics) file: one event per stop, which Google Calendar, Apple
// Calendar and Outlook all import. Times are written as "floating" local times (no time zone),
// so 9:30 AM in Rome shows as 9:30 AM whatever time zone the traveler's phone is set to.

import { mapsLink } from "./links";
import type { Itinerary } from "./types";

// RFC 5545 text escaping: backslash, semicolon, comma and newlines.
function escapeText(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
}

// Lines longer than 75 octets are folded onto continuation lines that start with a space.
function fold(line: string): string {
  const bytes = new TextEncoder().encode(line);
  if (bytes.length <= 75) return line;
  const parts: string[] = [];
  let current = "";
  let size = 0;
  for (const char of line) {
    const charSize = new TextEncoder().encode(char).length;
    const limit = parts.length === 0 ? 75 : 74; // continuation lines start with a space
    if (size + charSize > limit) {
      parts.push(current);
      current = "";
      size = 0;
    }
    current += char;
    size += charSize;
  }
  parts.push(current);
  return parts.join("\r\n ");
}

// "2026-12-10" + "09:30" -> "20261210T093000" (floating local time).
function localDateTime(date: string, time: string): string {
  return `${date.replace(/-/g, "")}T${time.replace(":", "")}00`;
}

function utcStamp(now: Date): string {
  return now.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
}

/** The whole plan as an .ics file's text (CRLF line endings, as the standard requires). */
export function itineraryToIcs(itinerary: Itinerary, now: Date = new Date()): string {
  const city = itinerary.destination.name;
  const stamp = utcStamp(now);
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Wanderwise//Trip plan//EN",
    "CALSCALE:GREGORIAN",
    `X-WR-CALNAME:${escapeText(`Wanderwise: ${city}`)}`,
  ];
  itinerary.days.forEach((day, dayIndex) => {
    day.items.forEach((item, i) => {
      const name = item.name?.trim() || item.place_id;
      const map = mapsLink(item, city);
      const details = [item.reason, item.description, `Map: ${map}`, item.website ? `Website: ${item.website}` : ""]
        .filter(Boolean)
        .join("\n");
      lines.push(
        "BEGIN:VEVENT",
        `UID:${escapeText(`${itinerary.trip_id}-${dayIndex}-${i}@wanderwise`)}`,
        `DTSTAMP:${stamp}`,
        `DTSTART:${localDateTime(day.date, item.start)}`,
        `DTEND:${localDateTime(day.date, item.end)}`,
        `SUMMARY:${escapeText(name)}`,
        `LOCATION:${escapeText(`${name}, ${city}`)}`,
        `DESCRIPTION:${escapeText(details)}`,
        `URL:${map}`,
        "END:VEVENT",
      );
    });
  });
  lines.push("END:VCALENDAR");
  return lines.map(fold).join("\r\n") + "\r\n";
}

/** "wanderwise-rome-italy-2026-12-10.ics" */
export function icsFileName(itinerary: Itinerary): string {
  const slug = itinerary.destination.name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return `wanderwise-${slug || "trip"}-${itinerary.start_date}.ics`;
}

/** Start a download of the plan's calendar file in the browser. */
export function downloadIcs(itinerary: Itinerary): void {
  const blob = new Blob([itineraryToIcs(itinerary)], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = icsFileName(itinerary);
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
