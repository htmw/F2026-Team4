import { useState } from "react";

import { postFeedback, postPlan } from "./api";
import type { Feedback } from "./api";
import { ItineraryView } from "./ItineraryView";
import { PreferenceForm } from "./PreferenceForm";
import type { Itinerary, PlanRequest } from "./types";

export function App() {
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [rejected, setRejected] = useState<string[]>([]);
  const [replanning, setReplanning] = useState(false);

  async function handleSubmit(req: PlanRequest) {
    setSubmitting(true);
    setError(null);
    try {
      setItinerary(await postPlan(req));
      setRejected([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setItinerary(null);
    } finally {
      setSubmitting(false);
    }
  }

  function toggleReject(placeId: string) {
    setRejected((prev) =>
      prev.includes(placeId)
        ? prev.filter((id) => id !== placeId)
        : [...prev, placeId],
    );
  }

  async function handleReplan() {
    if (!itinerary) return;
    setReplanning(true);
    setError(null);
    try {
      const feedback: Feedback = { accepted: [], rejected };
      setItinerary(await postFeedback(itinerary.trip_id, feedback));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setReplanning(false);
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Wanderwise</h1>
        <p className="muted">
          Walking skeleton — the scheduler is a naive stub. Real optimization comes next.
        </p>
      </header>

      <main className="layout">
        <PreferenceForm onSubmit={handleSubmit} submitting={submitting} />
        <div>
          {error && <div className="card error">Could not plan the trip: {error}</div>}
          {itinerary ? (
            <ItineraryView
              itinerary={itinerary}
              rejected={rejected}
              onToggleReject={toggleReject}
              onReplan={handleReplan}
              replanning={replanning}
            />
          ) : (
            !error && <div className="card muted">Fill the form and submit to see an itinerary.</div>
          )}
        </div>
      </main>
    </div>
  );
}
