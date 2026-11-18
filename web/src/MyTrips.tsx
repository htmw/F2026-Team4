import { useEffect, useRef, useState } from "react";

import { formatDateRange } from "./format";
import { FoldedMapIcon } from "./icons";
import { savedTrips as defaultClient } from "./savedTrips";
import type { SavedTrip, SavedTripsClient } from "./savedTrips";
import type { User } from "./auth";

interface Props {
  user: User;
  onOpen: (trip: SavedTrip) => void;
  onPlanNew: () => void;
  // The trip being opened, while it loads, and a failure to open one.
  opening?: string | null;
  openError?: string | null;
  client?: SavedTripsClient;
}

export function MyTrips({ user, onOpen, onPlanNew, opening, openError, client = defaultClient }: Props) {
  const [trips, setTrips] = useState<SavedTrip[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  useEffect(() => {
    let live = true;
    setError(null);
    client
      .list(user)
      .then((list) => live && setTrips(list))
      .catch((err: unknown) => live && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      live = false;
    };
  }, [client, user]);

  async function remove(trip: SavedTrip) {
    try {
      await client.remove(user, trip.trip_id);
      setTrips((list) => (list ?? []).filter((t) => t.trip_id !== trip.trip_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <section className="panel my-trips" aria-labelledby="my-trips-title">
      <div className="my-trips-header">
        <h2 id="my-trips-title" ref={headingRef} tabIndex={-1} className="panel-title">
          My trips
        </h2>
        <button type="button" className="button-secondary button-small" onClick={onPlanNew}>
          Plan a new trip
        </button>
      </div>

      {(error || openError) && (
        <p className="field-error" role="alert">
          {openError ?? error}
        </p>
      )}

      {trips === null && !error && <p className="muted">Loading your trips…</p>}

      {trips && trips.length === 0 && (
        <div className="my-trips-empty">
          <FoldedMapIcon className="my-trips-empty-icon" />
          <p>No saved trips yet. Plan a trip, then press <strong>Save trip</strong> to keep it here.</p>
        </div>
      )}

      {trips && trips.length > 0 && (
        <ul className="trip-list">
          {trips.map((trip) => (
            <li key={trip.trip_id} className="trip-card">
              <div className="trip-card-body">
                <h3 className="trip-card-title">{trip.destination}</h3>
                <p className="trip-card-meta">
                  {formatDateRange(trip.start_date, trip.end_date)} · {trip.days}{" "}
                  {trip.days === 1 ? "day" : "days"}
                </p>
              </div>
              <div className="trip-card-actions">
                <button
                  type="button"
                  className="button-primary button-small"
                  disabled={opening === trip.trip_id}
                  onClick={() => onOpen(trip)}
                  aria-label={`Open ${trip.destination} trip`}
                >
                  {opening === trip.trip_id ? "Opening…" : "Open"}
                </button>
                <button
                  type="button"
                  className="button-quiet button-small"
                  onClick={() => remove(trip)}
                  aria-label={`Remove ${trip.destination} trip from My trips`}
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
