import type { Confidence, DayWeather } from "./types";

export function formatMoney(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

// "09:30" -> "9:30 AM", "13:05" -> "1:05 PM", "00:00" -> "12:00 AM". Anything else as is.
export function formatTime(hhmm: string): string {
  const match = /^(\d{1,2}):(\d{2})$/.exec(hhmm);
  if (!match) return hhmm;
  const hours = Number(match[1]);
  if (hours > 23) return hhmm;
  const suffix = hours < 12 ? "AM" : "PM";
  return `${hours % 12 === 0 ? 12 : hours % 12}:${match[2]} ${suffix}`;
}

// [["10:00", "18:00"]] -> "Open 10:00 AM – 6:00 PM"; two windows are joined with "and";
// open all day -> "Open 24 hours". Empty when there are no hours to show.
export function openHoursLabel(windows?: [string, string][]): string {
  if (!windows || windows.length === 0) return "";
  if (windows.length === 1 && windows[0][0] === "00:00" && windows[0][1] >= "23:59") {
    return "Open 24 hours";
  }
  // Hours that run to the end of the day are stored as 23:59: say "midnight".
  const closing = (close: string) => (close >= "23:59" ? "midnight" : formatTime(close));
  const parts = windows.map(([open, close]) => `${formatTime(open)} – ${closing(close)}`);
  return `Open ${parts.join(" and ")}`;
}

// How we surface data confidence to the user (see DESIGN.md — the system says so
// instead of pretending, where the data is thin).
export function confidenceLabel(confidence: Confidence): string {
  switch (confidence) {
    case "known":
      return "verified";
    case "inferred":
      return "estimated";
    default:
      return "unverified";
  }
}

// Turn "fixture:cervejaria-ramiro" into "Cervejaria Ramiro" for display.
// Temporary: once items carry real names (or the UI fetches place details), drop this.
export function prettifyPlaceId(placeId: string): string {
  const tail = placeId.includes(":") ? placeId.split(":").slice(1).join(":") : placeId;
  return tail
    .split("-")
    .map((word) => (word.length ? word[0].toUpperCase() + word.slice(1) : word))
    .join(" ");
}

// "Free" when nobody pays, "≈ ₹700" for a typical estimate, "Price unknown" when no one knows.
// An itinerary without cost_confidence (older trips) just shows the amount.
export function priceLabel(cost: number, currency: string, confidence?: Confidence): string {
  if (confidence === "unknown") return "Price unknown";
  if (confidence && cost === 0) return "Free";
  if (confidence === "inferred") return `≈ ${formatMoney(cost, currency)}`;
  return formatMoney(cost, currency);
}

// "2026-10-01" -> "Thu, 1 Oct" (the exact wording follows the browser's locale).
// Dates are parsed and formatted in UTC so a calendar date never shifts by a day.
function parseIsoDate(iso: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return null;
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
}

export function formatDay(iso: string, locale?: string): string {
  const date = parseIsoDate(iso);
  if (!date) return iso;
  return new Intl.DateTimeFormat(locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(date);
}

// "2026-12-10" -> "Thu, 1 Oct 2026", with the year placed the way the locale expects.
function formatDayWithYear(date: Date, locale?: string): string {
  return new Intl.DateTimeFormat(locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

// "2026-12-10", "2026-12-12" -> "Thu, 10 Dec – Sat, 12 Dec 2026".
export function formatDateRange(startIso: string, endIso: string, locale?: string): string {
  const start = parseIsoDate(startIso);
  const end = parseIsoDate(endIso);
  if (!start || !end) return `${startIso} → ${endIso}`;
  if (startIso === endIso) return formatDayWithYear(start, locale);
  const startText =
    start.getUTCFullYear() === end.getUTCFullYear()
      ? formatDay(startIso, locale)
      : formatDayWithYear(start, locale);
  return `${startText} – ${formatDayWithYear(end, locale)}`;
}

// "09:30", "11:00" -> "9:30 AM - 11:00 AM".
export function formatTimeRange(start: string, end: string): string {
  return `${formatTime(start)} - ${formatTime(end)}`;
}

// The interests named in the optimizer's reason, strongest first:
// "Matches your interests in history, architecture and nature." -> ["history", "architecture", "nature"].
function reasonInterests(reason: string): string[] {
  const match = /^Matches your interests? in (.+?)\.?$/.exec(reason.trim());
  if (!match) return [];
  return match[1].split(/, | and /).map((name) => name.trim()).filter(Boolean);
}

// The optimizer's reason as a short label: "Matches your interest: history", or
// "Matches your interests: history, architecture" for several. Other reasons are shown as
// they are, without the full stop.
export function interestLabel(reason: string): string {
  const names = reasonInterests(reason);
  if (names.length === 1) return `Matches your interest: ${names[0]}`;
  if (names.length > 1) return `Matches your interests: ${names.join(", ")}`;
  return reason.trim().replace(/\.$/, "");
}

// The strongest interest named in the optimizer's reason ("history"), used to pick the stop's
// map-legend symbol; null when the reason names none.
export function interestFromReason(reason: string): string | null {
  const names = reasonInterests(reason);
  return names.length ? names[0].toLowerCase() : null;
}

// "Rain likely · 85% · 11–15 °C", "Sunny · 12–19 °C". Empty when there is no forecast.
export function weatherLabel(weather?: DayWeather): string {
  if (!weather) return "";
  const parts = [weather.summary];
  if (weather.rainy && weather.rain_probability != null) parts.push(`${weather.rain_probability}%`);
  const lo = weather.temp_min_c;
  const hi = weather.temp_max_c;
  if (lo != null && hi != null) parts.push(`${Math.round(lo)}–${Math.round(hi)} °C`);
  return parts.join(" · ");
}
