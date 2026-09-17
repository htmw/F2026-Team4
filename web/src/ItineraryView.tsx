import { confidenceLabel, formatMoney, prettifyPlaceId } from "./format";
import type { Itinerary } from "./types";

interface Props {
  itinerary: Itinerary;
}

export function ItineraryView({ itinerary }: Props) {
  const { destination, totals, warnings, score } = itinerary;
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

      {itinerary.days.map((day) => (
        <section key={day.date} className="day">
          <h3>{day.date}</h3>
          {day.items.length === 0 && <p className="muted">No stops scheduled.</p>}
          <ol className="timeline">
            {day.items.map((item, i) => (
              <li key={`${item.place_id}-${i}`} className="stop">
                <div className="stop-time">
                  {item.start}–{item.end}
                </div>
                <div className="stop-body">
                  <div className="stop-title">
                    {prettifyPlaceId(item.place_id)}
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
                </div>
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}
