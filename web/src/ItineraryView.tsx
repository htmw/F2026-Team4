import { useEffect, useState } from "react";

import { confidenceLabel, formatMoney, prettifyPlaceId } from "./format";
import type { Itinerary } from "./types";

interface Props {
  itinerary: Itinerary;
  rejected: string[];
  onToggleReject: (placeId: string) => void;
  onReplan: () => void;
  replanning: boolean;
}

export function ItineraryView({
  itinerary,
  rejected,
  onToggleReject,
  onReplan,
  replanning,
}: Props) {
  const { destination, totals, warnings, score } = itinerary;
  const [dayIndex, setDayIndex] = useState(0);

  // A new plan (or a re-plan) starts back on Day 1.
  useEffect(() => {
    setDayIndex(0);
  }, [itinerary]);

  const day = itinerary.days[dayIndex];
  return (
    <div className="card">
      <div className="itinerary-header">
        <h2>{destination.name}</h2>
        <div className="totals">
          <span>{formatMoney(totals.cost, totals.currency)}</span>
          {typeof score === "number" && <span>score {score.toFixed(2)}</span>}
        </div>
      </div>

      {warnings && warnings.length > 0 && (
        <ul className="warnings">
          {warnings.map((w, i) => (
            <li key={i}>⚠ {w}</li>
          ))}
        </ul>
      )}

      {itinerary.days.length > 1 && (
        <div className="day-nav">
          <button
            type="button"
            className="day-nav-button"
            disabled={dayIndex === 0}
            onClick={() => setDayIndex(dayIndex - 1)}
          >
            ← Previous day
          </button>
          <div className="day-steps">
            {itinerary.days.map((d, i) => (
              <button
                key={d.date}
                type="button"
                className={`day-step${i === dayIndex ? " day-step-active" : ""}`}
                aria-label={`Day ${i + 1}: ${d.date}`}
                onClick={() => setDayIndex(i)}
              >
                {i + 1}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="day-nav-button"
            disabled={dayIndex === itinerary.days.length - 1}
            onClick={() => setDayIndex(dayIndex + 1)}
          >
            Next day →
          </button>
        </div>
      )}

      {day ? (
        <section key={day.date} className="day">
          <h3>{day.date}</h3>
          {day.items.length === 0 && <p className="muted">No stops scheduled.</p>}
          <ol className="timeline">
            {day.items.map((item, i) => {
              const isRejected = rejected.includes(item.place_id);
              return (
                <li
                  key={`${item.place_id}-${i}`}
                  className={`stop${isRejected ? " stop-rejected" : ""}`}
                >
                  <div className="stop-time">
                    {item.start}–{item.end}
                  </div>
                  <div className="stop-body">
                    <div className="stop-title">
                      {item.name ?? prettifyPlaceId(item.place_id)}
                      {item.confidence !== "known" && (
                        <span className={`badge badge-${item.confidence}`}>
                          {confidenceLabel(item.confidence)}
                        </span>
                      )}
                    </div>
                    <div className="stop-reason">{item.reason}</div>
                    <div className="stop-meta">
                      {formatMoney(item.cost, totals.currency)}
                      {item.travel_from_prev && item.travel_from_prev.minutes > 0 && (
                        <> · {item.travel_from_prev.minutes} min {item.travel_from_prev.mode}</>
                      )}
                    </div>
                    <div className="stop-feedback">
                      <button
                        type="button"
                        className={`feedback-button${isRejected ? " feedback-remove-active" : ""}`}
                        aria-pressed={isRejected}
                        onClick={() => onToggleReject(item.place_id)}
                      >
                        ✕ Remove
                      </button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
      ) : (
        <p className="muted">No days scheduled.</p>
      )}

      {rejected.length > 0 && (
        <div className="feedback-bar">
          <span>
            {rejected.length} place{rejected.length === 1 ? "" : "s"} marked for
            removal. They will be left out of the new plan.
          </span>
          <button
            type="button"
            className="feedback-replan"
            disabled={replanning}
            onClick={onReplan}
          >
            {replanning ? "Re-planning…" : "Re-plan trip"}
          </button>
        </div>
      )}
    </div>
  );
}
