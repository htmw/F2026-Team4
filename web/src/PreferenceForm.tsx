import { useState } from "react";

import { INTEREST_KEYS } from "./interests";
import type { PlanRequest, TravelerProfile } from "./types";

const DEFAULT_INTERESTS: Record<string, number> = {
  food: 0.9,
  history: 0.8,
  art: 0.5,
  architecture: 0.7,
  nature: 0.4,
  nightlife: 0.2,
  shopping: 0.1,
};

const DIETARY_OPTIONS = [
  "vegetarian",
  "vegan",
  "halal",
  "kosher",
  "gluten-free",
  "nut allergy",
  "lactose-free",
];

interface Props {
  onSubmit: (req: PlanRequest) => void;
  submitting: boolean;
}

export function PreferenceForm({ onSubmit, submitting }: Props) {
  const [destination, setDestination] = useState("Lisbon");
  const [startDate, setStartDate] = useState("2026-10-01");
  const [endDate, setEndDate] = useState("2026-10-03");
  const [interests, setInterests] = useState<Record<string, number>>({ ...DEFAULT_INTERESTS });
  const [pace, setPace] = useState(0.4);
  const [maxWalk, setMaxWalk] = useState("20");
  const [dayStart, setDayStart] = useState("09:30");
  const [dayEnd, setDayEnd] = useState("22:00");
  const [budget, setBudget] = useState("1200");
  const [currency] = useState("EUR");
  const [dietary, setDietary] = useState<string[]>(["vegetarian"]);
  const [formError, setFormError] = useState<string | null>(null);

  function setInterest(key: string, value: number) {
    setInterests((prev) => ({ ...prev, [key]: value }));
    setFormError(null);
  }

  function toggleDietary(option: string) {
    setDietary((prev) =>
      prev.includes(option) ? prev.filter((d) => d !== option) : [...prev, option]
    );
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (endDate < startDate) {
      setFormError("End date can't be before the start date.");
      return;
    }
    if (dayEnd <= dayStart) {
      setFormError("Day end time must be later than the day start time.");
      return;
    }
    if (!Object.values(interests).some((v) => v > 0)) {
      setFormError("Please set at least one interest above zero so we know what you care about.");
      return;
    }
    setFormError(null);

    const maxWalkMinutes = Math.max(0, Number(maxWalk) || 0);
    const budgetTotal = Math.max(0, Number(budget) || 0);

    const profile: TravelerProfile = {
      interests,
      pace,
      max_walk_minutes: maxWalkMinutes,
      daily_active_hours: 8,
      day_start: dayStart,
      day_end: dayEnd,
      budget: { total: budgetTotal, currency },
      dietary,
      accessibility: [],
      avoid: [],
      novelty_appetite: 0.3,
      feedback: { accepted: [], rejected: [] },
    };
    onSubmit({
      profile,
      destination: { name: destination },
      start_date: startDate,
      end_date: endDate,
    });
  }

  return (
    <form className="card" onSubmit={handleSubmit}>
      <h2>Plan your perfect trip</h2>

      <div className="row">
        <label className="field">
          Destination
          <input value={destination} onChange={(e) => setDestination(e.target.value)} />
        </label>
        <label className="field">
          Start date
          <input
            type="date"
            value={startDate}
            onChange={(e) => {
              setStartDate(e.target.value);
              setFormError(null);
            }}
          />
        </label>
        <label className="field">
          End date
          <input
            type="date"
            value={endDate}
            min={startDate}
            onChange={(e) => {
              setEndDate(e.target.value);
              setFormError(null);
            }}
          />
        </label>
      </div>

      <h3>What do you care about?</h3>
      <div className="interests">
        {INTEREST_KEYS.map((key) => (
          <label key={key} className="slider">
            <span className="slider-label">
              {key} <em>{(interests[key] ?? 0).toFixed(1)}</em>
            </span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.1}
              value={interests[key] ?? 0}
              onChange={(e) => setInterest(key, Number(e.target.value))}
            />
          </label>
        ))}
      </div>

      <h3>Travel style</h3>
      <div className="row">
        <label className="slider">
          <span className="slider-label">
            pace <em>{pace.toFixed(1)}</em> (0 relaxed → 1 packed)
          </span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.1}
            value={pace}
            onChange={(e) => setPace(Number(e.target.value))}
          />
        </label>
        <label className="field">
          Max walk between stops (min)
          <input
            type="number"
            min={0}
            max={240}
            value={maxWalk}
            onChange={(e) => setMaxWalk(e.target.value)}
          />
        </label>
      </div>

      <div className="row">
        <label className="field">
          Day start
          <input
            type="time"
            value={dayStart}
            onChange={(e) => {
              setDayStart(e.target.value);
              setFormError(null);
            }}
          />
        </label>
        <label className="field">
          Day end
          <input
            type="time"
            value={dayEnd}
            onChange={(e) => {
              setDayEnd(e.target.value);
              setFormError(null);
            }}
          />
        </label>
        <label className="field">
          Budget ({currency})
          <input
            type="number"
            min={0}
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
          />
        </label>
      </div>

      <fieldset className="field">
        <legend>Dietary preferences</legend>
        <div className="checkbox-group">
          {DIETARY_OPTIONS.map((option) => (
            <label key={option} className="checkbox">
              <input
                type="checkbox"
                checked={dietary.includes(option)}
                onChange={() => toggleDietary(option)}
              />
              {option}
            </label>
          ))}
        </div>
      </fieldset>

      {formError && (
        <p className="form-error" role="alert">
          {formError}
        </p>
      )}

      <button type="submit" disabled={submitting}>
        {submitting ? "Planning…" : "Plan my trip"}
      </button>
    </form>
  );
}
