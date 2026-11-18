import { useEffect, useRef, useState } from "react";

import { ApiError, getTrip, postFeedback, postPlan } from "./api";
import type { Feedback } from "./api";
import { auth } from "./auth";
import type { User } from "./auth";
import { formatDateRange, prettifyPlaceId } from "./format";
import { FoldedMapIcon, InterestIcon, UserIcon } from "./icons";
import { ItineraryView } from "./ItineraryView";
import type { RemovedPlace, SaveControl } from "./ItineraryView";
import { shareLink } from "./links";
import { LoginPage } from "./LoginPage";
import { MyTrips } from "./MyTrips";
import { PreferenceForm } from "./PreferenceForm";
import { navigate, useRoute } from "./route";
import { savedTrips } from "./savedTrips";
import { SharedTrip } from "./SharedTrip";
import type { SavedTrip } from "./savedTrips";
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
  // A destination the server rejected, shown on the Destination field.
  const [destinationError, setDestinationError] = useState<{ message: string; seq: number } | null>(null);
  // The request behind the plan on screen, for the one-line trip summary.
  const [lastRequest, setLastRequest] = useState<PlanRequest | null>(null);
  // On phones the form collapses into a one-line summary once a plan exists, so the plan
  // is what the traveler sees first. Desktop always shows both (see .planner in CSS).
  const [formOpen, setFormOpen] = useState(true);
  // Places removed by the last re-plan, for the "Removed … · Undo" note.
  const [lastRemoved, setLastRemoved] = useState<RemovedPlace[] | null>(null);
  const [undoing, setUndoing] = useState(false);
  // A failed re-plan or undo is shown next to the re-plan controls, not in the top banner.
  const [replanError, setReplanError] = useState<string | null>(null);

  const route = useRoute();
  // undefined while we check whether someone is already logged in.
  const [user, setUser] = useState<User | null | undefined>(undefined);
  // Trip ids in the user's My trips, so the plan on screen can say it's already saved.
  const [savedIds, setSavedIds] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);

  useEffect(() => {
    auth
      .current()
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  useEffect(() => {
    if (!user) {
      setSavedIds([]);
      return;
    }
    let live = true;
    savedTrips
      .list(user)
      .then((list) => live && setSavedIds(list.map((t) => t.trip_id)))
      .catch(() => live && setSavedIds([]));
    return () => {
      live = false;
    };
  }, [user]);

  async function saveTrip(who: User, plan: Itinerary) {
    setSaving(true);
    setSaveError(null);
    try {
      await savedTrips.save(who, plan, lastRequest);
      setSavedIds((ids) => (ids.includes(plan.trip_id) ? ids : [...ids, plan.trip_id]));
    } catch (err) {
      setSaveError(`Couldn't save the trip: ${sentence(err)}`);
    } finally {
      setSaving(false);
    }
  }

  function handleSave() {
    if (!itinerary) return;
    if (!user) {
      navigate({ page: "login", next: "save" });
      return;
    }
    void saveTrip(user, itinerary);
  }

  function handleLoggedIn(who: User) {
    setUser(who);
    if (route.page === "login" && route.next === "save" && itinerary) {
      void saveTrip(who, itinerary);
      navigate({ page: "plan" });
    } else {
      navigate({ page: "trips" });
    }
  }

  async function handleLogOut() {
    await auth.logOut();
    setUser(null);
    setSaveError(null);
    navigate({ page: "plan" });
  }

  async function openSavedTrip(trip: SavedTrip) {
    setOpening(trip.trip_id);
    setOpenError(null);
    try {
      const plan = await getTrip(trip.trip_id);
      setItinerary(plan);
      setLastRequest(trip.request ?? null);
      setRejected([]);
      setLastRemoved(null);
      setReplanError(null);
      setError(null);
      setFormOpen(false);
      navigate({ page: "plan" });
    } catch (err) {
      setOpenError(`Couldn't open the ${trip.destination} trip: ${sentence(err)}`);
    } finally {
      setOpening(null);
    }
  }

  const saveControl: SaveControl | undefined = itinerary
    ? {
        status: savedIds.includes(itinerary.trip_id) ? "saved" : saving ? "saving" : "unsaved",
        onSave: handleSave,
        error: saveError,
      }
    : undefined;

  async function handleSubmit(req: PlanRequest) {
    setSubmitting(true);
    setError(null);
    setDestinationError(null);
    setPlanningFor(req.destination.name);
    // On narrow screens the results sit below the long form; bring them into view.
    revealResults(resultsRef.current);
    try {
      setItinerary(await postPlan(req));
      setLastRequest(req);
      setRejected([]);
      setLastRemoved(null);
      setReplanError(null);
      setSaveError(null);
      setFormOpen(false);
    } catch (err) {
      // Keep the plan that is already on screen: a failed new request shouldn't destroy it.
      if (err instanceof ApiError && err.field === "destination") {
        setDestinationError({ message: err.message, seq: Date.now() });
        setFormOpen(true);
      } else {
        setError(`Could not plan the trip: ${sentence(err)}`);
      }
    } finally {
      setSubmitting(false);
    }
  }

  function toggleReject(placeId: string) {
    setReplanError(null);
    setRejected((prev) =>
      prev.includes(placeId)
        ? prev.filter((id) => id !== placeId)
        : [...prev, placeId],
    );
  }

  async function handleReplan() {
    if (!itinerary) return;
    setReplanning(true);
    setReplanError(null);
    const removed = removedPlaces(itinerary, rejected);
    try {
      const feedback: Feedback = { accepted: [], rejected };
      setItinerary(await postFeedback(itinerary.trip_id, feedback));
      setRejected([]);
      setLastRemoved(removed);
    } catch (err) {
      setReplanError(`Couldn't re-plan the trip: ${sentence(err)} Your plan hasn't changed.`);
    } finally {
      setReplanning(false);
    }
  }

  // Undo a removal: the backend drops a place from the rejected list when it is sent as
  // accepted (api/main.py, _merge_feedback), then re-plans.
  async function handleUndo() {
    if (!itinerary || !lastRemoved) return;
    setUndoing(true);
    setError(null);
    try {
      const feedback: Feedback = { accepted: lastRemoved.map((p) => p.id), rejected: [] };
      setItinerary(await postFeedback(itinerary.trip_id, feedback));
      setLastRemoved(null);
    } catch (err) {
      setError(`Couldn't undo the removal: ${sentence(err)}`);
    } finally {
      setUndoing(false);
    }
  }

  function openForm() {
    setFormOpen(true);
    requestAnimationFrame(() => {
      document.getElementById("plan-form")?.scrollIntoView({ block: "start" });
      document.querySelector<HTMLElement>("#plan-form h3")?.focus();
    });
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-inner">
          <h1 className="wordmark">
            <a href="#/" className="wordmark-link">
              <FoldedMapIcon className="wordmark-mark" />
              Wanderwise
            </a>
          </h1>
          <p className="app-tagline">Day plans you can actually walk</p>
          <AccountNav user={user} onLogOut={handleLogOut} />
        </div>
      </header>

      {route.page === "login" || (route.page === "trips" && user === null) ? (
        <main className="page">
          <LoginPage
            onLoggedIn={handleLoggedIn}
            onCancel={() => navigate({ page: "plan" })}
            reason={
              route.page === "trips"
                ? "Log in to see your saved trips."
                : route.next === "save"
                  ? "Log in or create an account to save this trip. Your plan stays as it is."
                  : null
            }
          />
        </main>
      ) : route.page === "shared" ? (
        <main className="page page-wide">
          <SharedTrip tripId={route.tripId} />
        </main>
      ) : route.page === "trips" ? (
        <main className="page">
          {user && (
            <MyTrips
              user={user}
              onOpen={openSavedTrip}
              onPlanNew={() => navigate({ page: "plan" })}
              opening={opening}
              openError={openError}
            />
          )}
        </main>
      ) : (
      <main className="layout">
        <div className={`planner${formOpen ? "" : " planner-collapsed"}`}>
          {lastRequest && (
            <div className="panel trip-summary">
              <p>
                <strong>{lastRequest.destination.name}</strong>
                <span className="trip-summary-dates">
                  {formatDateRange(lastRequest.start_date, lastRequest.end_date)}
                </span>
              </p>
              <button
                type="button"
                className="button-secondary"
                aria-expanded={false}
                aria-controls="plan-form"
                onClick={openForm}
              >
                Edit trip
              </button>
            </div>
          )}
          <PreferenceForm
            onSubmit={handleSubmit}
            submitting={submitting}
            destinationError={destinationError}
          />
        </div>
        <div ref={resultsRef} className="results">
          {error && (
            <div className="panel error-panel" role="alert">
              {error}
              {itinerary && !submitting && " Your current plan is still below."}
            </div>
          )}
          {submitting ? (
            <PlanningMessage city={planningFor} />
          ) : itinerary ? (
            <ItineraryView
              itinerary={itinerary}
              request={lastRequest}
              rejected={rejected}
              onToggleReject={toggleReject}
              onReplan={handleReplan}
              replanning={replanning}
              lastRemoved={lastRemoved}
              replanError={replanError}
              onUndo={handleUndo}
              undoing={undoing}
              save={saveControl}
              shareUrl={shareLink(itinerary.trip_id)}
            />
          ) : (
            !error &&
            !destinationError && (
              <div className="panel empty-state">
                <div className="empty-route" aria-hidden="true">
                  <span className="stop-pin pin-history">
                    <InterestIcon interest="history" />
                  </span>
                  <span className="empty-path" />
                  <span className="stop-pin pin-food">
                    <InterestIcon interest="food" />
                  </span>
                  <span className="empty-path" />
                  <span className="stop-pin pin-nature">
                    <InterestIcon interest="nature" />
                  </span>
                </div>
                <h2 className="panel-title">Your plan appears here</h2>
                <p>
                  A day-by-day schedule with times, travel between stops and costs, checked against
                  your budget and walking limit. Each stop says whether its opening hours are
                  verified.
                </p>
              </div>
            )
          )}
        </div>
      </main>
      )}
    </div>
  );
}

function AccountNav({ user, onLogOut }: { user: User | null | undefined; onLogOut: () => void }) {
  if (user === undefined) return <nav className="account-nav" aria-label="Account" />;
  return (
    <nav className="account-nav" aria-label="Account">
      {user ? (
        <>
          <a href="#/trips" className="account-link">
            My trips
          </a>
          <span className="account-name">
            <UserIcon />
            {user.name}
          </span>
          <button type="button" className="account-button" onClick={onLogOut}>
            Log out
          </button>
        </>
      ) : (
        <a href="#/login" className="account-link">
          <UserIcon />
          Log in
        </a>
      )}
    </nav>
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
    <div className="panel planning" role="status">
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

// Names of the places about to be removed, read from the plan before it is replaced.
function removedPlaces(itinerary: Itinerary, ids: string[]): RemovedPlace[] {
  return ids.map((id) => {
    const item = itinerary.days.flatMap((day) => day.items).find((i) => i.place_id === id);
    return { id, name: item?.name ?? prettifyPlaceId(id) };
  });
}

// An error's message as a sentence: capitalised and ending in a full stop, so it reads
// correctly when followed by more text ("… Your plan hasn't changed.").
function sentence(err: unknown): string {
  const text = (err instanceof Error ? err.message : String(err)).trim();
  if (!text) return "Something went wrong.";
  const capitalised = text[0].toUpperCase() + text.slice(1);
  return /[.!?]$/.test(capitalised) ? capitalised : `${capitalised}.`;
}
