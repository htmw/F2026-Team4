import { useEffect, useRef, useState } from "react";

import { confidenceLabel, formatDay, formatMoney, prettifyPlaceId } from "./format";
import { AlertIcon, ChevronLeft, ChevronRight, CloseIcon } from "./icons";
import type { Itinerary, PlanRequest } from "./types";

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
}: Props) {
  const { destination, totals, warnings, score } = itinerary;
  const [dayIndex, setDayIndex] = useState(0);
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

  const day = itinerary.days[dayIndex];
  const lastDay = itinerary.days.length - 1;

  return (
    <article className="panel plan" aria-labelledby="plan-title">
      <header className="plan-header">
        <h2 id="plan-title" ref={headingRef} tabIndex={-1} className="plan-title">
          {destination.name}
        </h2>
        {request && <p className="plan-dates">{dayCountLabel(itinerary.days.length)}</p>}
      </header>

      <FitSummary itinerary={itinerary} request={request} score={score} />

      {lastRemoved && lastRemoved.length > 0 && (
        <div className="notice" role="status" ref={noticeRef} tabIndex={-1}>
          <p>Removed {listNames(lastRemoved.map((p) => p.name))} and re-planned the trip.</p>
          <button type="button" className="button-secondary button-small" disabled={undoing} onClick={onUndo}>
            {undoing ? "Undoing…" : "Undo"}
          </button>
        </div>
      )}

      {warnings && warnings.length > 0 && (
        <div className="callout callout-warn">
          <AlertIcon className="callout-icon" />
          <ul aria-label="Things to know about this plan">
            {warnings.map((warning, i) => (
              <li key={i}>{warning}</li>
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
        <section key={day.date} className="day" aria-labelledby="day-title">
          <h3 id="day-title" className="day-title">
            Day {dayIndex + 1} <span className="day-date">{formatDay(day.date)}</span>
          </h3>
          {day.items.length > 0 && <p className="day-totals">{dayTotals(day, totals.currency)}</p>}
          {day.items.length === 0 && <p className="muted">Nothing scheduled this day.</p>}
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
                <li key={`${item.place_id}-${i}`} className={`stop${isRejected ? " is-rejected" : ""}`}>
                  {travel && travel.minutes > 0 && (
                    <p className={`stop-travel${walkOver > 0 ? " is-over" : ""}`}>
                      {walkOver > 0 && <AlertIcon />}
                      {travel.minutes} min {travel.mode} from the previous stop
                      {walkOver > 0 && `, ${walkOver} min over your ${walkLimit}-min limit`}
                    </p>
                  )}
                  <div className="stop-row">
                    <p className="stop-time">
                      <time>{item.start}</time>
                      <span className="visually-hidden"> to </span>
                      <time>{item.end}</time>
                    </p>
                    <div className="stop-body">
                      <h4 className="stop-name">{name}</h4>
                      <p className="stop-reason">{item.reason}</p>
                      <p className="stop-meta">
                        <span className={`confidence confidence-${item.confidence}`}>
                          Hours {confidenceLabel(item.confidence)}
                        </span>
                        <span className="stop-cost">{formatMoney(item.cost, totals.currency)}</span>
                      </p>
                    </div>
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
                          Remove
                        </>
                      )}
                    </button>
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
      ) : (
        <p className="muted">Nothing scheduled.</p>
      )}

      <details className="legend">
        <summary>What do "verified", "estimated" and "unverified" mean?</summary>
        <dl>
          <dt>Hours verified</dt>
          <dd>Opening hours come from the place's own listing, so the plan treats them as fixed.</dd>
          <dt>Hours estimated</dt>
          <dd>No listed hours, so typical hours for this kind of place were used. Check before you go.</dd>
          <dt>Hours unverified</dt>
          <dd>We couldn't find opening hours. The place may be closed when you arrive.</dd>
        </dl>
      </details>

      {rejected.length > 0 && (
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
      <div className={`fit-item${overBudget > 0 ? " is-over" : ""}`}>
        <dt>Cost</dt>
        <dd>
          <strong>{formatMoney(totals.cost, totals.currency)}</strong>
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
      <div className={`fit-item${overWalk ? " is-over" : ""}`}>
        <dt>Walking</dt>
        <dd>
          <strong>{totals.walking_minutes} min</strong>
          <span>
            {!walks.length
              ? "in total"
              : overWalk
                ? `in total · longest walk ${longestWalk} min, ${longestWalk - (walkLimit ?? 0)} min over your ${walkLimit}-min limit`
                : `in total · longest walk ${longestWalk} min${walkLimit !== undefined ? `, within your ${walkLimit}-min limit` : ""}`}
          </span>
        </dd>
      </div>
      {profile && (
        <div className="fit-item">
          <dt>Daily hours</dt>
          <dd>
            <strong>
              {profile.day_start}–{profile.day_end}
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

// "3 stops · 45 min walking · ¥6,800" for one day.
function dayTotals(day: Itinerary["days"][number], currency: string): string {
  const stops = day.items.length;
  const walking = day.items.reduce(
    (sum, item) => sum + (item.travel_from_prev?.mode === "walk" ? item.travel_from_prev.minutes : 0),
    0,
  );
  const cost = day.items.reduce((sum, item) => sum + item.cost, 0);
  return [
    `${stops} ${stops === 1 ? "stop" : "stops"}`,
    `${walking} min walking`,
    formatMoney(cost, currency),
  ].join(" · ");
}

function dayCountLabel(days: number): string {
  return days === 1 ? "1 day" : `${days} days`;
}

// ["A"] -> "A"; ["A", "B"] -> "A and B"; ["A", "B", "C"] -> "A, B and C".
function listNames(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}
