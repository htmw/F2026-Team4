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
  const [maxWalk, setMaxWalk] = useState(20);
  const [dayStart, setDayStart] = useState("09:30");
  const [dayEnd, setDayEnd] = useState("22:00");
  const [budget, setBudget] = useState(1200);
  const [currency] = useState("EUR");
  const [dietary, setDietary] = useState("vegetarian");

  function setInterest(key: string, value: number) {
    setInterests((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const profile: TravelerProfile = {
      interests,
      pace,
      max_walk_minutes: maxWalk,
      daily_active_hours: 8,
      day_start: dayStart,
      day_end: dayEnd,
      budget: { total: budget, currency },
      dietary: dietary
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
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
      <h2>Plan a trip</h2>

      <div className="row">
        <label className="field">
          Destination
          <input value={destination} onChange={(e) => setDestination(e.target.value)} />
        </label>
        <label className="field">
          Start date
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        </label>
        <label className="field">
          End date
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
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
            onChange={(e) => setMaxWalk(Number(e.target.value))}
          />
        </label>
      </div>

      <div className="row">
        <label className="field">
          Day start
          <input type="time" value={dayStart} onChange={(e) => setDayStart(e.target.value)} />
        </label>
        <label className="field">
          Day end
          <input type="time" value={dayEnd} onChange={(e) => setDayEnd(e.target.value)} />
        </label>
        <label className="field">
          Budget ({currency})
          <input
            type="number"
            min={0}
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
          />
        </label>
      </div>

      <label className="field">
        Dietary (comma-separated)
        <input value={dietary} onChange={(e) => setDietary(e.target.value)} />
      </label>

      <button type="submit" disabled={submitting}>
        {submitting ? "Planning…" : "Plan my trip"}
      </button>
    </form>
  );
}
