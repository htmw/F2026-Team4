import { useState } from "react";

import { postPlan } from "./api";
import { ItineraryView } from "./ItineraryView";
import { PreferenceForm } from "./PreferenceForm";
import type { Itinerary, PlanRequest } from "./types";

export function App() {
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(req: PlanRequest) {
    setSubmitting(true);
    setError(null);
    try {
      setItinerary(await postPlan(req));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setItinerary(null);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Travel Recommender</h1>
        <p className="muted">
          Walking skeleton — the scheduler is a naive stub. Real optimization comes next.
        </p>
      </header>

      <main className="layout">
        <PreferenceForm onSubmit={handleSubmit} submitting={submitting} />
        <div>
          {error && <div className="card error">Could not plan the trip: {error}</div>}
          {itinerary ? (
            <ItineraryView itinerary={itinerary} />
          ) : (
            !error && <div className="card muted">Fill the form and submit to see an itinerary.</div>
          )}
        </div>
      </main>
    </div>
  );
}
