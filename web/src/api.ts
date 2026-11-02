import type { Itinerary, PlanRequest } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

// The backend returns errors as JSON like {"detail": {"destination_errors": [...]}}.
// Pull out the human-readable message instead of showing the raw body.
function readableError(kind: string, status: number, detail: string): Error {
  try {
    const parsed = JSON.parse(detail) as { detail?: unknown };
    const inner = parsed.detail;
    if (typeof inner === "string" && inner) {
      return new Error(inner);
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
        return new Error(messages.join(" "));
      }
      if (typeof fields.message === "string" && fields.message) {
        return new Error(fields.message);
      }
    }
  } catch {
    // Not JSON — fall through to the raw fallback below.
  }
  if (!detail) {
    return new Error(`${kind} request failed (${status})`);
  }
  return new Error(`${kind} request failed (${status}): ${detail}`);
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
