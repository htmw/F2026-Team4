
import { confidenceLabel, formatMoney, prettifyPlaceId } from "./format";
import type { Itinerary } from "./types";

interface Props {
  itinerary: Itinerary;
}

export function ItineraryView({ itinerary }: Props) {
  const { destination, totals, warnings, score, days } = itinerary;

  return (
    <div className="card itinerary-dashboard">
      <div className="itinerary-dashboard-header">
        <div>
          <p className="itinerary-eyebrow">YOUR PERSONALIZED TRIP</p>
          <h2>📍 {destination.name}</h2>
          <p className="muted">Your day-by-day travel itinerary</p>
        </div>
      </div>

      <div className="trip-summary">
        <div className="summary-card">
          <span>📅 Duration</span>
          <strong>{days.length} days</strong>
        </div>

        <div className="summary-card">
          <span>💰 Estimated cost</span>
          <strong>{formatMoney(totals.cost, totals.currency)}</strong>
        </div>

        <div className="summary-card">
          <span>⭐ Score</span>
          <strong>
            {typeof score === "number" ? score.toFixed(2) : "N/A"}
          </strong>
        </div>
      </div>

      {warnings && warnings.length > 0 && (
        <ul className="warnings">
          {warnings.map((warning, i) => (
            <li key={i}>⚠ {warning}</li>
          ))}
        </ul>
      )}

      <div className="itinerary-days">
        {days.map((day, dayIndex) => (
          <section key={day.date} className="itinerary-day-card">
            <div className="itinerary-day-header">
              <div>
                <span className="day-number">DAY {dayIndex + 1}</span>
                <h3>{day.date}</h3>
              </div>
              <span className="day-count">
                {day.items.length} activities
              </span>
            </div>

            {day.items.length === 0 && (
              <p className="muted">No stops scheduled.</p>
            )}

            <ol className="itinerary-activities">
              {day.items.map((item, i) => (
                <li
                  key={`${item.place_id}-${i}`}
                  className="itinerary-activity"
                >
                  <div className="activity-icon">📍</div>

                  <div className="activity-content">
                    <div className="activity-time">
                      🕒 {item.start}–{item.end}
                    </div>

                    <div className="activity-title">
                      <strong>{prettifyPlaceId(item.place_id)}</strong>

                      {item.confidence !== "known" && (
                        <span
                          className={`badge badge-${item.confidence}`}
                        >
                          {confidenceLabel(item.confidence)}
                        </span>
                      )}
                    </div>

                    <p className="activity-reason">{item.reason}</p>

                    <div className="activity-meta">
                      <span>
                        💶 {formatMoney(item.cost, totals.currency)}
                      </span>

                      {item.travel_from_prev &&
                        item.travel_from_prev.minutes > 0 && (
                          <span>
                            🚶 {item.travel_from_prev.minutes} min{" "}
                            {item.travel_from_prev.mode}
                          </span>
                        )}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        ))}
      </div>
    </div>
  );
}
