// "My trips": the trips a logged-in user saved.
//
// The backend already stores every planned trip under its trip_id (GET /trips/{id} returns
// its latest plan, re-plans included). What's new is the list of which trips belong to whom.
// - demo mode: that list lives in this browser, per account.
// - server mode: the backend's /me/trips endpoints (see web/BACKEND-HANDOFF.md).
// Either way a saved trip opens through GET /trips/{id}, so it's always the latest plan.

import { API_BASE } from "./api";
import { auth, browserStore, readJson } from "./auth";
import type { AuthClient, KeyValueStore, User } from "./auth";
import type { Itinerary, PlanRequest } from "./types";

export interface SavedTrip {
  trip_id: string;
  destination: string;
  start_date: string;
  end_date: string;
  days: number;
  saved_at: string;
  // The form answers the plan was made from, so a reopened trip still shows the traveler's
  // budget and walking limit. Missing when the trip was saved without them.
  request?: PlanRequest | null;
}

export interface SavedTripsClient {
  list(user: User): Promise<SavedTrip[]>;
  save(user: User, itinerary: Itinerary, request: PlanRequest | null): Promise<SavedTrip>;
  remove(user: User, tripId: string): Promise<void>;
}

export class SavedTripsError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SavedTripsError";
  }
}

export function summarise(itinerary: Itinerary, request: PlanRequest | null, now = new Date()): SavedTrip {
  return {
    trip_id: itinerary.trip_id,
    destination: itinerary.destination.name,
    start_date: itinerary.start_date,
    end_date: itinerary.end_date,
    days: itinerary.days.length,
    saved_at: now.toISOString(),
    request,
  };
}

// Newest first.
function byNewest(trips: SavedTrip[]): SavedTrip[] {
  return [...trips].sort((a, b) => b.saved_at.localeCompare(a.saved_at));
}

export function createDemoSavedTrips(store: KeyValueStore = browserStore()): SavedTripsClient {
  const key = (user: User) => `wanderwise.demo.trips.${user.id}`;
  const read = (user: User) => readJson<SavedTrip[]>(store, key(user), []);
  return {
    async list(user) {
      return byNewest(read(user));
    },
    async save(user, itinerary, request) {
      const trip = summarise(itinerary, request);
      // Saving again updates the entry instead of adding a second one.
      const others = read(user).filter((t) => t.trip_id !== trip.trip_id);
      store.setItem(key(user), JSON.stringify([trip, ...others]));
      return trip;
    },
    async remove(user, tripId) {
      store.setItem(key(user), JSON.stringify(read(user).filter((t) => t.trip_id !== tripId)));
    },
  };
}

export function createServerSavedTrips(client: AuthClient = auth, base: string = API_BASE): SavedTripsClient {
  async function call(path: string, init: RequestInit = {}): Promise<Response> {
    const resp = await fetch(`${base}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...client.authHeaders(), ...(init.headers ?? {}) },
    });
    if (resp.status === 401) throw new SavedTripsError("Your session has ended. Log in again to see your trips.");
    if (!resp.ok) throw new SavedTripsError(`Couldn't reach your saved trips (error ${resp.status}). Try again.`);
    return resp;
  }
  return {
    async list() {
      return byNewest((await (await call("/me/trips")).json()) as SavedTrip[]);
    },
    async save(_user, itinerary, request) {
      const resp = await call(`/me/trips/${encodeURIComponent(itinerary.trip_id)}`, {
        method: "PUT",
        body: JSON.stringify({ request }),
      });
      return (await resp.json()) as SavedTrip;
    },
    async remove(_user, tripId) {
      await call(`/me/trips/${encodeURIComponent(tripId)}`, { method: "DELETE" });
    },
  };
}

export const savedTrips: SavedTripsClient =
  import.meta.env.VITE_AUTH_MODE === "server" ? createServerSavedTrips() : createDemoSavedTrips();
