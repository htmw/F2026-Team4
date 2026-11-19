import { useEffect, useRef, useState } from "react";

import {
  confidenceLabel,
  formatDay,
  formatMoney,
  formatTime,
  formatTimeRange,
  interestFromReason,
  interestLabel,
  openHoursLabel,
  prettifyPlaceId,
  priceLabel,
  weatherLabel,
} from "./format";
import { downloadIcs } from "./calendar";
import {
  AlertIcon,
  BookmarkIcon,
  CalendarIcon,
  CheckIcon,
  ChevronLeft,
  ChevronRight,
  CloseIcon,
  ExternalIcon,
  InterestIcon,
  PinIcon,
  PlusIcon,
  PrintIcon,
  SwapIcon,
} from "./icons";
import { DayMap } from "./DayMap";
import { dayRouteLink, mapsLink, ticketLink } from "./links";
import { ShareButton } from "./ShareButton";
import { StopSuggestions } from "./StopSuggestions";
import type { Suggestion } from "./api";
import type { Itinerary, ItineraryItem, PlanRequest } from "./types";

export interface RemovedPlace {
  id: string;
  name: string;
}

interface Props {
  itinerary: Itinerary;
  // The request behind this plan, so the plan can show the traveler's own limits.
  request: PlanRequest | null;
  rejected: string[];
  onToggleReject: (placeId: string) => void;
  onReplan: () => void;
  replanning: boolean;
  // Places the last re-plan removed, for the "Removed … · Undo" note.
  lastRemoved: RemovedPlace[] | null;
  onUndo: () => void;
  undoing: boolean;
  // A failed re-plan or undo, shown next to the re-plan controls rather than at the top.
  replanError?: string | null;
  // "Save trip" to My trips. Left out, the button isn't shown.
  save?: SaveControl;
  // "Share" copies a read-only link to this trip. Left out, the button isn't shown.
  shareUrl?: string;
  // A shared trip opened from a link: no Remove, Re-plan or Undo.
  readOnly?: boolean;
  // Swap a stop for another place, or add one to a day; resolves once re-planned.
  // Left out, the Swap and Add buttons aren't shown.
  onChangeStop?: (change: StopChange) => Promise<void>;
  // What the last swap or add did ("Swapped … for …"), or why it couldn't.
  changeNote?: { text: string; ok: boolean } | null;
}

export interface StopChange {
  add: Suggestion;
  replace?: { id: string; name: string };
}

type OpenPanel = { kind: "swap"; placeId: string } | { kind: "add"; date: string } | null;

export interface SaveControl {
  status: "unsaved" | "saving" | "saved";
  onSave: () => void;
  error?: string | null;
}

export function ItineraryView({
  itinerary,
  request,
  rejected,
  onToggleReject,
  onReplan,
  replanning,
  lastRemoved,
  onUndo,
  undoing,
  replanError,
  save,
  shareUrl,
  readOnly = false,
  onChangeStop,
  changeNote,
}: Props) {
  const { destination, totals, warnings, score } = itinerary;
  const [dayIndex, setDayIndex] = useState(0);
  // The open "Swap" or "Add a place" list, if any.
  const [openPanel, setOpenPanel] = useState<OpenPanel>(null);
  const canChange = !readOnly && onChangeStop !== undefined;
  // A new plan (from a swap, add or re-plan) closes the list.
  useEffect(() => setOpenPanel(null), [itinerary]);
  // "Save as PDF" renders every day, opens the browser's print dialog, then returns to one day.
  const [printing, setPrinting] = useState(false);
  useEffect(() => {
    if (!printing) return;
    const done = () => setPrinting(false);
    window.addEventListener("afterprint", done);
    const frame = requestAnimationFrame(() => {
      window.print();
      done();
    });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("afterprint", done);
    };
  }, [printing]);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const tripRef = useRef<string | null>(null);
  const noticeRef = useRef<HTMLDivElement>(null);
  const replanErrorRef = useRef<HTMLParagraphElement>(null);
  const walkLimit = request?.profile.max_walk_minutes;

  // After a re-plan, the Re-plan button is gone; move focus (and the screen) to the note that
  // says what changed and offers Undo, instead of leaving focus on the page body.
  useEffect(() => {
    if (lastRemoved && lastRemoved.length > 0) noticeRef.current?.focus();
  }, [lastRemoved]);

  useEffect(() => {
    if (replanError) replanErrorRef.current?.focus();
  }, [replanError]);

  // A new trip starts on Day 1 and focus moves to its heading, so screen reader users hear
  // that it arrived (focusing also scrolls it into view on a phone). A re-plan of the same
  // trip stays on the day the traveler was looking at; the "Removed …" note announces it.
  useEffect(() => {
    if (tripRef.current !== itinerary.trip_id) {
      tripRef.current = itinerary.trip_id;
      setDayIndex(0);
      headingRef.current?.focus();
    } else {
      setDayIndex((current) => Math.min(current, Math.max(itinerary.days.length - 1, 0)));
    }
  }, [itinerary]);

  const notes = planNotes(itinerary, warnings ?? []);
  const day = itinerary.days[dayIndex];
  const lastDay = itinerary.days.length - 1;

  return (
    <article className="panel plan" aria-labelledby="plan-title">
      <header className="plan-header">
        <h2 id="plan-title" ref={headingRef} tabIndex={-1} className="plan-title">
          {destination.name}
        </h2>
        {request && <p className="plan-dates">{dayCountLabel(itinerary.days.length)}</p>}
        <div className="plan-export" role="group" aria-label="Save or export this plan">
          {save && <SaveButton save={save} />}
          {shareUrl && <ShareButton url={shareUrl} />}
          <button type="button" className="button-secondary button-small" onClick={() => downloadIcs(itinerary)}>
            <CalendarIcon />
            Add to calendar
          </button>
          <button type="button" className="button-secondary button-small" onClick={() => setPrinting(true)}>
            <PrintIcon />
            Save as PDF
          </button>
        </div>
      </header>

      {save?.error && (
        <p className="field-error plan-save-error" role="alert">
          {save.error}
        </p>
      )}

      <FitSummary itinerary={itinerary} request={request} score={score} />

      {!readOnly && lastRemoved && lastRemoved.length > 0 && (
        <div className="notice" role="status" ref={noticeRef} tabIndex={-1}>
          <p>Removed {listNames(lastRemoved.map((p) => p.name))} and re-planned the trip.</p>
          <button type="button" className="button-secondary button-small" disabled={undoing} onClick={onUndo}>
            {undoing ? "Undoing…" : "Undo"}
          </button>
        </div>
      )}

      {changeNote && (
        <div className={`notice${changeNote.ok ? "" : " notice-warn"}`} role="status">
          <p>{changeNote.text}</p>
        </div>
      )}

      {notes.length > 0 && (
        <div className="callout callout-warn">
          <AlertIcon className="callout-icon" />
          <ul aria-label="Things to know about this plan">
            {notes.map((note, i) => (
              <li key={i}>{note}</li>
            ))}
          </ul>
        </div>
      )}

      {itinerary.days.length > 1 && (
        <nav className="day-nav" aria-label="Days">
          <button
            type="button"
            className="button-secondary button-small day-nav-prev"
            disabled={dayIndex === 0}
            onClick={() => setDayIndex(dayIndex - 1)}
          >
            <ChevronLeft />
            Previous day
          </button>
          <div className="day-steps">
            {itinerary.days.map((d, i) => (
              <button
                key={d.date}
                type="button"
                className={`day-step${i === dayIndex ? " is-current" : ""}`}
                aria-label={`Day ${i + 1}, ${formatDay(d.date)}`}
                aria-current={i === dayIndex ? "date" : undefined}
                onClick={() => setDayIndex(i)}
              >
                {i + 1}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="button-secondary button-small day-nav-next"
            disabled={dayIndex === lastDay}
            onClick={() => setDayIndex(dayIndex + 1)}
          >
            Next day
            <ChevronRight />
          </button>
        </nav>
      )}

      {day ? (
        // On screen one day at a time; when saving as PDF, every day in order.
        (printing ? itinerary.days : [day]).map((day) => {
        const dayNumber = itinerary.days.indexOf(day) + 1;
        return (
        <section key={day.date} className="day" aria-labelledby={`day-title-${dayNumber}`}>
          <h3 id={`day-title-${dayNumber}`} className="day-title">
            Day {dayNumber} <span className="day-date">{formatDay(day.date)}</span>
          </h3>
          {day.weather && (
            <p className={`day-weather${day.weather.rainy ? " is-rainy" : ""}`}>
              {weatherLabel(day.weather)}
            </p>
          )}
          {day.items.length > 0 && (
            <p className="day-totals">
              {dayTotals(day, totals.currency)}
              {dayRouteLink(day.items, destination.name) && (
                <a
                  className="day-route-link"
                  href={dayRouteLink(day.items, destination.name)!}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Day route in Google Maps
                  <ExternalIcon />
                  <span className="visually-hidden"> (opens in a new tab)</span>
                </a>
              )}
            </p>
          )}
          {day.items.length === 0 && <p className="muted">Nothing scheduled this day.</p>}
          {!printing && <DayMap items={day.items} dayNumber={dayNumber} />}
          <ol className="timeline">
            {day.items.map((item, i) => {
              const isRejected = rejected.includes(item.place_id);
              const name = item.name ?? prettifyPlaceId(item.place_id);
              const travel = item.travel_from_prev;
              const walkOver =
                travel && travel.mode === "walk" && walkLimit !== undefined && travel.minutes > walkLimit
                  ? travel.minutes - walkLimit
                  : 0;
              return (
                <li
                  key={`${item.place_id}-${i}`}
                  className={`stop${isRejected ? " is-rejected" : ""}${walkOver > 0 ? " is-walk-over" : ""}`}
                >
                  {/* The day drawn as a walking route: a pin with the stop's map-legend symbol,
                      joined to the previous stop by a dashed footpath. */}
                  <div className="stop-rail" aria-hidden="true">
                    <span className={`stop-pin pin-${interestFromReason(item.reason) ?? "other"}`}>
                      <InterestIcon interest={interestFromReason(item.reason)} />
                    </span>
                  </div>
                  <div className="stop-main">
                  {travel && travel.minutes > 0 && (
                    <p className={`stop-travel${walkOver > 0 ? " is-over" : ""}`}>
                      {walkOver > 0 && <AlertIcon />}
                      {travel.minutes} min {travel.mode} from the previous stop
                      {travel.mode === "transit" && travel.walk_minutes
                        ? ` (incl. ${travel.walk_minutes} min walk to and from the stop)`
                        : ""}
                      {walkOver > 0 && `, ${walkOver} min over your ${walkLimit}-min limit`}
                    </p>
                  )}
                  <div className="stop-row">
                    <div className="stop-body">
                      <p className="stop-time">{formatTimeRange(item.start, item.end)}</p>
                      <div className="stop-heading">
                        <h4 className="stop-name">{name}</h4>
                        <span className="stop-interest">{interestLabel(item.reason)}</span>
                      </div>
                      {item.description && (
                        <p className="stop-description">
                          {item.description}
                          {item.description_source === "wikipedia" && (
                            <span className="stop-source"> (Wikipedia)</span>
                          )}
                        </p>
                      )}
                      <p className="stop-meta">
                        {item.open_hours && item.open_hours.length > 0 && (
                          <span className="stop-hours">{openHoursLabel(item.open_hours)}</span>
                        )}
                        {item.confidence !== "unknown" && (
                          <span className={`confidence confidence-${item.confidence}`}>
                            Hours {confidenceLabel(item.confidence)}
                          </span>
                        )}
                        <span className="stop-cost">
                          {priceLabel(item.cost, totals.currency, item.cost_confidence)}
                        </span>
                      </p>
                      <StopLinks item={item} name={name} city={destination.name} />
                    </div>
                    <div className="stop-actions">
                    {canChange && !isRejected && (
                      <button
                        type="button"
                        className="swap-button"
                        aria-expanded={openPanel?.kind === "swap" && openPanel.placeId === item.place_id}
                        aria-label={`Swap ${name} for another place`}
                        onClick={() =>
                          setOpenPanel(
                            openPanel?.kind === "swap" && openPanel.placeId === item.place_id
                              ? null
                              : { kind: "swap", placeId: item.place_id },
                          )
                        }
                      >
                        <SwapIcon />
                        <span className="remove-label">Swap</span>
                      </button>
                    )}
                    {!readOnly && (
                    <button
                      type="button"
                      className={`remove-button${isRejected ? " is-active" : ""}`}
                      aria-pressed={isRejected}
                      aria-label={isRejected ? `Keep ${name}` : `Remove ${name}`}
                      onClick={() => onToggleReject(item.place_id)}
                    >
                      {isRejected ? (
                        "Keep"
                      ) : (
                        <>
                          <CloseIcon />
                          <span className="remove-label">Remove</span>
                        </>
                      )}
                    </button>
                    )}
                    </div>
                  </div>
                  {canChange && openPanel?.kind === "swap" && openPanel.placeId === item.place_id && (
                    <StopSuggestions
                      tripId={itinerary.trip_id}
                      currency={totals.currency}
                      replace={{ id: item.place_id, name }}
                      date={day.date}
                      dayNumber={dayNumber}
                      onChoose={(s) => onChangeStop!({ add: s, replace: { id: item.place_id, name } })}
                      onClose={() => setOpenPanel(null)}
                    />
                  )}
                  </div>
                </li>
              );
            })}
          </ol>
          {canChange && !printing && (
            openPanel?.kind === "add" && openPanel.date === day.date ? (
              <StopSuggestions
                tripId={itinerary.trip_id}
                currency={totals.currency}
                date={day.date}
                dayNumber={dayNumber}
                onChoose={(s) => onChangeStop!({ add: s })}
                onClose={() => setOpenPanel(null)}
              />
            ) : (
              <button
                type="button"
                className="button-quiet add-stop-button"
                onClick={() => setOpenPanel({ kind: "add", date: day.date })}
              >
                <PlusIcon />
                Add a place to Day {dayNumber}
              </button>
            )
          )}
        </section>
        );
        })
      ) : (
        <p className="muted">Nothing scheduled.</p>
      )}

      <details className="legend">
        <summary>What do "verified" and "estimated" mean?</summary>
        <dl>
          <dt>Verified</dt>
          <dd>Opening hours come from the place's own listing, so the plan treats them as fixed.</dd>
          <dt>Estimated</dt>
          <dd>
            No listed hours or price, so typical ones for this kind of place were used (estimated
            prices are shown with ≈). Check before you go.
          </dd>
        </dl>
      </details>

      {!readOnly && rejected.length > 0 && (
        <div className="replan-bar">
          {replanError && (
            <p className="replan-error" role="alert" tabIndex={-1} ref={replanErrorRef}>
              {replanError}
            </p>
          )}
          <p>
            {rejected.length} {rejected.length === 1 ? "place" : "places"} marked for removal. They'll be left
            out of the new plan.
          </p>
          <button type="button" className="button-primary" disabled={replanning} onClick={onReplan}>
            {replanning ? "Re-planning…" : "Re-plan trip"}
          </button>
        </div>
      )}
    </article>
  );
}

// The traveler's own limits next to what the plan actually uses, so the plan shows that it
// fits before showing any stops (PRODUCT.md, principles 2 and 3).
function FitSummary({
  itinerary,
  request,
  score,
}: {
  itinerary: Itinerary;
  request: PlanRequest | null;
  score?: number;
}) {
  const { totals } = itinerary;
  const profile = request?.profile;
  const budget = profile?.budget;
  const budgetApplies = budget && budget.currency === totals.currency;
  const overBudget = budgetApplies ? totals.cost - budget.total : 0;
  const walks = itinerary.days.flatMap((day) =>
    day.items.flatMap((item) =>
      item.travel_from_prev && item.travel_from_prev.mode === "walk" ? [item.travel_from_prev.minutes] : [],
    ),
  );
  const longestWalk = walks.length ? Math.max(...walks) : 0;
  const walkLimit = profile?.max_walk_minutes;
  const overWalk = walkLimit !== undefined && longestWalk > walkLimit;

  return (
    <dl className="fit">
      <div className={`fit-item${overWalk ? " is-over" : ""}`}>
        {walks.length > 0 ? (
          <>
            <dt>Longest walk</dt>
            <dd>
              <strong>{longestWalk} min</strong>
              {walkLimit !== undefined && walkLimit > 0 && (
                <ScaleBar value={longestWalk} limit={walkLimit} label={`${walkLimit} min`} />
              )}
              <span>
                {overWalk
                  ? `${longestWalk - (walkLimit ?? 0)} min over your ${walkLimit}-min limit · ${totals.walking_minutes} min walking in total`
                  : `${walkLimit !== undefined ? `Within your ${walkLimit}-min limit · ` : ""}${totals.walking_minutes} min walking in total`}
              </span>
            </dd>
          </>
        ) : (
          <>
            <dt>Walking</dt>
            <dd>
              <strong>{totals.walking_minutes} min</strong>
              <span>in total</span>
            </dd>
          </>
        )}
      </div>
      <div className={`fit-item${overBudget > 0 ? " is-over" : ""}`}>
        <dt>Cost</dt>
        <dd>
          <strong>{formatMoney(totals.cost, totals.currency)}</strong>
          {budgetApplies && budget.total > 0 && (
            <ScaleBar value={totals.cost} limit={budget.total} label={formatMoney(budget.total, budget.currency)} />
          )}
          <span>
            {budgetApplies
              ? overBudget > 0
                ? `${formatMoney(overBudget, totals.currency)} over your ${formatMoney(budget.total, budget.currency)} budget`
                : `of your ${formatMoney(budget.total, budget.currency)} budget`
              : budget
                ? `Budget in ${budget.currency} not applied: prices here are in ${totals.currency}`
                : "Total for the trip"}
          </span>
        </dd>
      </div>
      {profile && (
        <div className="fit-item">
          <dt>Daily hours</dt>
          <dd>
            <strong>
              <span className="nowrap">{formatTime(profile.day_start)}</span> -{" "}
              <span className="nowrap">{formatTime(profile.day_end)}</span>
            </strong>
            <span>as you asked</span>
          </dd>
        </div>
      )}
      {typeof score === "number" && (
        <div className="fit-item">
          <dt>Interest match</dt>
          <dd>
            <strong>{Math.round(score * 100)}%</strong>
            <span>how well the stops fit what you said you love</span>
          </dd>
        </div>
      )}
    </dl>
  );
}

// The optimizer's warnings, with its count-only note about unverified opening hours replaced by
// one that names the places ("Opening hours aren't listed for teamLab Planets (Day 1). Check
// before you go."), so travelers know which stops to check. Stops don't carry an "unverified"
// label, so this note is where that information lives.
function planNotes(itinerary: Itinerary, warnings: string[]): string[] {
  const unlisted = itinerary.days.flatMap((day, i) =>
    day.items
      .filter((item) => item.confidence === "unknown")
      .map((item) => `${item.name ?? prettifyPlaceId(item.place_id)} (Day ${i + 1})`),
  );
  if (unlisted.length === 0) return warnings;
  const shown = unlisted.slice(0, 3);
  const more = unlisted.length - shown.length;
  const names = more > 0 ? `${shown.join(", ")} and ${more} more` : listNames(shown);
  const note = `Opening hours aren't listed for ${names}. Check before you go.`;
  const others = warnings.filter((warning) => !/^Opening hours are unverified/i.test(warning));
  return [note, ...others];
}

// "3 stops · 45 min walking · ¥6,800" for one day.
// Links beside a stop: Google Maps, and for a paid tourist attraction its official website for
// tickets when the data has one. They open in a new tab so the plan stays where it was.
function StopLinks({ item, name, city }: { item: ItineraryItem; name: string; city: string }) {
  const tickets = ticketLink(item, interestFromReason(item.reason));
  return (
    <p className="stop-links">
      <a href={mapsLink(item, city)} target="_blank" rel="noopener noreferrer" aria-label={`${name} in Google Maps (opens in a new tab)`}>
        <PinIcon />
        Map
      </a>
      {tickets && (
        <a href={tickets.href} target="_blank" rel="noopener noreferrer" aria-label={`Tickets for ${name} on the official website (opens in a new tab)`}>
          <ExternalIcon />
          Tickets
        </a>
      )}
    </p>
  );
}

// A map-style scale bar: the track runs to the traveler's limit (the tick), the fill shows what the
// plan uses. Past the limit the track extends and the overflow is drawn in the warning colour.
// Decorative: the text next to it says the same thing.
function ScaleBar({ value, limit, label }: { value: number; limit: number; label: string }) {
  // Within the limit the bar ends at the limit's tick; only an overflow extends the bar past it,
  // so there is never an empty stretch after the tick.
  const over = value > limit;
  const span = over ? value * 1.05 : limit;
  const share = (n: number) => Math.min(100, (n / span) * 100);
  const pct = (n: number) => `${share(n).toFixed(1)}%`;
  const tickAtEnd = share(limit) > 92;
  return (
    <span className={`scale${over ? " is-over" : ""}`} aria-hidden="true">
      <span className="scale-fill" style={{ width: pct(Math.min(value, limit)) }} />
      {over && <span className="scale-over" style={{ left: pct(limit), width: pct(value - limit) }} />}
      <span className="scale-tick" style={{ left: pct(limit) }} />
      <span
        className="scale-label"
        style={tickAtEnd ? { right: 0, transform: "none" } : { right: `calc(100% - ${pct(limit)})` }}
      >
        {label}
      </span>
    </span>
  );
}

function dayTotals(day: Itinerary["days"][number], currency: string): string {
  const stops = day.items.length;
  const walking = day.items.reduce((sum, item) => sum + walkMinutes(item.travel_from_prev), 0);
  const cost = day.items.reduce((sum, item) => sum + item.cost, 0);
  return [
    `${stops} ${stops === 1 ? "stop" : "stops"}`,
    `${walking} min walking`,
    formatMoney(cost, currency),
  ].join(" · ");
}

// Walking in one move: the walk to and from the stop counts for a transit ride too.
// Older trips without walk_minutes count only walks, as before.
function walkMinutes(travel?: { minutes: number; mode: string; walk_minutes?: number }): number {
  if (!travel) return 0;
  if (travel.walk_minutes !== undefined) return travel.walk_minutes;
  return travel.mode === "walk" ? travel.minutes : 0;
}

function dayCountLabel(days: number): string {
  return days === 1 ? "1 day" : `${days} days`;
}

// ["A"] -> "A"; ["A", "B"] -> "A and B"; ["A", "B", "C"] -> "A, B and C".
function listNames(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

function SaveButton({ save }: { save: SaveControl }) {
  if (save.status === "saved") {
    return (
      <span className="plan-saved" role="status">
        <CheckIcon />
        Saved to My trips
      </span>
    );
  }
  return (
    <button
      type="button"
      className="button-primary button-small"
      disabled={save.status === "saving"}
      onClick={save.onSave}
    >
      <BookmarkIcon />
      {save.status === "saving" ? "Saving…" : "Save trip"}
    </button>
  );
}
