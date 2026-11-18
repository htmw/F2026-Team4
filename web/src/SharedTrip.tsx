import { useEffect, useState } from "react";

import { getTrip } from "./api";
import { ItineraryView } from "./ItineraryView";
import type { Itinerary } from "./types";

const noop = () => {};

// A trip opened from a shared link: the latest plan, read only.
export function SharedTrip({ tripId, load = getTrip }: { tripId: string; load?: (id: string) => Promise<Itinerary> }) {
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setItinerary(null);
    setError(null);
    load(tripId)
      .then((plan) => live && setItinerary(plan))
      .catch((err: unknown) => live && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      live = false;
    };
  }, [tripId, load]);

  return (
    <>
      <div className="panel shared-banner">
        <p>
          <strong>A shared trip.</strong> You're seeing a read-only copy of someone's plan.
        </p>
        <a className="button-primary button-small" href="#/">
          Plan your own trip
        </a>
      </div>
      {error && (
        <div className="panel error-panel" role="alert">
          Couldn't open this trip. {error}
        </div>
      )}
      {!itinerary && !error && (
        <div className="panel planning" role="status">
          <p className="planning-title">
            <span className="planning-spinner" aria-hidden="true" />
            Opening the shared trip…
          </p>
        </div>
      )}
      {itinerary && (
        <ItineraryView
          itinerary={itinerary}
          request={null}
          rejected={[]}
          onToggleReject={noop}
          onReplan={noop}
          replanning={false}
          lastRemoved={null}
          onUndo={noop}
          undoing={false}
          readOnly
        />
      )}
    </>
  );
}
