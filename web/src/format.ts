import type { Confidence } from "./types";

export function formatMoney(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
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
