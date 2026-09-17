import type { Itinerary, PlanRequest } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export async function postPlan(req: PlanRequest): Promise<Itinerary> {
  const resp = await fetch(`${API_BASE}/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`Plan request failed (${resp.status}): ${detail}`);
  }
  return (await resp.json()) as Itinerary;
}
