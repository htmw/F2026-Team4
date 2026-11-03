import type { Itinerary, PlanRequest } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

// An API error with a readable message. `field` is set when the problem is a form field
// the user can fix (today: an unknown or invalid destination), so the form can show the
// message on that field instead of only in a banner.
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly field?: "destination",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// The backend returns errors as JSON like {"detail": {"destination_errors": [...]}}.
// Pull out the human-readable message instead of showing the raw body.
export function readableError(kind: string, status: number, detail: string): ApiError {
  const make = (message: string, field?: "destination") => new ApiError(message, status, field);
  try {
    const parsed = JSON.parse(detail) as { detail?: unknown };
    const inner = parsed.detail;
    if (typeof inner === "string" && inner) {
      return make(inner);
    }
    if (inner && typeof inner === "object") {
      const fields = inner as Record<string, unknown>;
      const messages: string[] = [];
      for (const value of Object.values(fields)) {
        if (Array.isArray(value) && value.length > 0) {
          messages.push(...value.map(String));
        }
      }
      if (messages.length > 0) {
        // A 422 with destination errors means the city itself is wrong ("'japan' is a
        // country, not a city"). A 503 uses the same key when OpenStreetMap is down, which
        // is not something the user can fix in the field.
        const destinationProblem =
          status === 422 && Array.isArray(fields.destination_errors) && fields.destination_errors.length > 0;
        return make(messages.join(" "), destinationProblem ? "destination" : undefined);
      }
      if (typeof fields.message === "string" && fields.message) {
        return make(fields.message);
      }
    }
  } catch {
    // Not JSON — fall through to the raw fallback below.
  }
  if (!detail) {
    return make(`${kind} request failed (${status})`);
  }
  return make(`${kind} request failed (${status}): ${detail}`);
}

export async function postPlan(req: PlanRequest): Promise<Itinerary> {
  const resp = await fetch(`${API_BASE}/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    throw readableError("Plan", resp.status, await resp.text());
  }
  return (await resp.json()) as Itinerary;
}

export interface Feedback {
  accepted: string[];
  rejected: string[];
}

export async function postFeedback(
  tripId: string,
  feedback: Feedback,
): Promise<Itinerary> {
  const resp = await fetch(
    `${API_BASE}/trips/${encodeURIComponent(tripId)}/feedback`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(feedback),
    },
  );
  if (!resp.ok) {
    throw readableError("Feedback", resp.status, await resp.text());
  }
  return (await resp.json()) as Itinerary;
}
