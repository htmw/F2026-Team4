import { useEffect, useRef, useState } from "react";

import { getSuggestions, SuggestionsUnavailable } from "./api";
import type { Suggestion } from "./api";
import { interestFromReason, interestLabel, priceLabel } from "./format";
import { InterestIcon } from "./icons";

interface Props {
  tripId: string;
  currency: string;
  // Swapping: the stop being replaced. Adding: left out.
  replace?: { id: string; name: string };
  date: string;
  dayNumber: number;
  // Resolves once the trip has been re-planned.
  onChoose: (suggestion: Suggestion) => Promise<void>;
  onClose: () => void;
  load?: typeof getSuggestions;
}

const SHOWN = 5;

export function StopSuggestions({ tripId, currency, replace, date, dayNumber, onChoose, onClose, load = getSuggestions }: Props) {
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  const [problem, setProblem] = useState<{ message: string; unavailable: boolean } | null>(null);
  const [choosing, setChoosing] = useState<string | null>(null);
  const [chooseError, setChooseError] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  useEffect(() => {
    let live = true;
    load(tripId, { replace: replace?.id, date })
      .then((list) => live && setSuggestions(list.slice(0, SHOWN)))
      .catch(
        (err: unknown) =>
          live &&
          setProblem({
            message: err instanceof Error ? err.message : String(err),
            unavailable: err instanceof SuggestionsUnavailable,
          }),
      );
    return () => {
      live = false;
    };
  }, [tripId, replace?.id, date, load]);

  async function choose(s: Suggestion) {
    setChoosing(s.place_id);
    setChooseError(null);
    try {
      await onChoose(s);
    } catch (err) {
      setChooseError(`Couldn't re-plan with ${s.name}: ${err instanceof Error ? err.message : String(err)} Your plan hasn't changed.`);
    } finally {
      setChoosing(null);
    }
  }

  const title = replace ? `Instead of ${replace.name}` : `Add a place to Day ${dayNumber}`;

  return (
    <section className="suggestions" aria-labelledby={`suggestions-title-${replace?.id ?? date}`}>
      <div className="suggestions-header">
        <h5 id={`suggestions-title-${replace?.id ?? date}`} ref={headingRef} tabIndex={-1} className="suggestions-title">
          {title}
        </h5>
        <button type="button" className="button-quiet button-small" onClick={onClose}>
          Cancel
        </button>
      </div>

      {chooseError && (
        <p className="field-error" role="alert">
          {chooseError}
        </p>
      )}

      {problem ? (
        <p className={problem.unavailable ? "muted" : "field-error"} role={problem.unavailable ? "status" : "alert"}>
          {problem.unavailable
            ? `${problem.message} For now, remove the stop and re-plan, and the planner picks something else.`
            : `Couldn't load ideas: ${problem.message}`}
        </p>
      ) : suggestions === null ? (
        <p className="muted" role="status">
          Finding places that fit…
        </p>
      ) : suggestions.length === 0 ? (
        <p className="muted" role="status">
          Nothing else fits this {replace ? "time" : "day"} with your interests, budget and walking limit.
        </p>
      ) : (
        <ul className="suggestion-list">
          {suggestions.map((s) => {
            const interest = interestFromReason(s.reason);
            return (
              <li key={s.place_id} className="suggestion">
                <span className={`stop-pin stop-pin-small pin-${interest ?? "other"}`} aria-hidden="true">
                  <InterestIcon interest={interest} />
                </span>
                <div className="suggestion-body">
                  <p className="suggestion-name">{s.name}</p>
                  <p className="suggestion-meta">
                    {interestLabel(s.reason)}
                    {s.cost !== undefined && <> · {priceLabel(s.cost, currency, s.cost_confidence)}</>}
                  </p>
                </div>
                <button
                  type="button"
                  className="button-secondary button-small"
                  disabled={choosing !== null}
                  onClick={() => choose(s)}
                  aria-label={replace ? `Use ${s.name} instead of ${replace.name}` : `Add ${s.name} to Day ${dayNumber}`}
                >
                  {choosing === s.place_id ? "Re-planning…" : replace ? "Use this" : "Add"}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
