import { useEffect, useRef, useState } from "react";

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
  // City being planned, shown in the loading message.
  const [planningFor, setPlanningFor] = useState("");
  const resultsRef = useRef<HTMLDivElement>(null);

  async function handleSubmit(req: PlanRequest) {
    setSubmitting(true);
    setError(null);
    setPlanningFor(req.destination.name);
    // On narrow screens the results sit below the long form; bring them into view.
    revealResults(resultsRef.current);
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
      setRejected([]);
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
      </header>

      <main className="layout">
        <PreferenceForm onSubmit={handleSubmit} submitting={submitting} />
        <div ref={resultsRef} className="results">
          {error && (
            <div className="card error" role="alert">
              Could not plan the trip: {error}
            </div>
          )}
          {submitting ? (
            <PlanningMessage city={planningFor} />
          ) : itinerary ? (
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

// Scroll the results into view only when they are off screen (the stacked phone layout).
function revealResults(element: HTMLElement | null) {
  if (!element) return;
  const { top } = element.getBoundingClientRect();
  if (top >= 0 && top < window.innerHeight * 0.5) return;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  element.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
}

// The first plan for a new city fetches live data from OpenStreetMap, which can take a
// minute; say so instead of leaving only a disabled button.
function PlanningMessage({ city }: { city: string }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), 8000);
    return () => window.clearTimeout(timer);
  }, []);
  return (
    <div className="card planning" role="status">
      <p className="planning-title">
        <span className="planning-spinner" aria-hidden="true" />
        Planning your trip to {city}…
      </p>
      <p className="muted">
        {slow
          ? "Still working. The first plan for a city fetches live places from OpenStreetMap, which can take about a minute."
          : "If this is the first trip planned for this city, we fetch live places from OpenStreetMap first. That can take about a minute."}
      </p>
    </div>
  );
}
