import { useRef, useState } from "react";
import type { FormEvent } from "react";

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

const STEPS = ["Trip details", "Preferences", "Review"] as const;

type Step = 0 | 1 | 2;
type Errors = Record<string, string>;

interface Props {
  onSubmit: (req: PlanRequest) => void;
  submitting: boolean;
}

export function PreferenceForm({ onSubmit, submitting }: Props) {
  const [step, setStep] = useState<Step>(0);
  const [errors, setErrors] = useState<Errors>({});

  // State stays here so switching steps preserves all inputs.
  const [destination, setDestination] = useState("Lisbon");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [interests, setInterests] = useState<Record<string, number>>({
    ...DEFAULT_INTERESTS,
  });

  const [pace, setPace] = useState(0.4);
  const [maxWalk, setMaxWalk] = useState("20");
  const [budget, setBudget] = useState("1200");
  const [dayStart, setDayStart] = useState("09:30");
  const [dayEnd, setDayEnd] = useState("22:00");
  const [dietary, setDietary] = useState("vegetarian");

  const currency = "EUR";
  const headingRef = useRef<HTMLHeadingElement>(null);
  const formRef = useRef<HTMLFormElement>(null);

  function changeStep(nextStep: Step) {
    setStep(nextStep);
    setErrors({});

    requestAnimationFrame(() => {
      headingRef.current?.focus();
    });
  }

  function clearError(field: string) {
    setErrors((previous) => {
      const next = { ...previous };
      delete next[field];
      return next;
    });
  }

  function validateTripDetails(): Errors {
    const next: Errors = {};

    if (!destination.trim()) {
      next.destination = "Please enter a destination.";
    }

    if (!startDate) {
      next.startDate = "Please select a start date.";
    }

    if (!endDate) {
      next.endDate = "Please select an end date.";
    } else if (startDate && endDate < startDate) {
      next.endDate = "End date cannot be earlier than start date.";
    }

    return next;
  }

  function validatePreferences(): Errors {
    const next: Errors = {};
    const walkingMinutes = Number(maxWalk);
    const totalBudget = Number(budget);

    if (
      !maxWalk.trim() ||
      !Number.isFinite(walkingMinutes) ||
      walkingMinutes < 0 ||
      walkingMinutes > 240
    ) {
      next.maxWalk = "Enter a walking limit between 0 and 240 minutes.";
    }

    if (
      !budget.trim() ||
      !Number.isFinite(totalBudget) ||
      totalBudget < 0
    ) {
      next.budget = "Enter a budget of 0 or more.";
    }

    if (!dayStart) {
      next.dayStart = "Please select a daily start time.";
    }

    if (!dayEnd) {
      next.dayEnd = "Please select a daily end time.";
    } else if (dayStart && dayEnd <= dayStart) {
      next.dayEnd = "End time must be later than start time.";
    }

    return next;
  }

  function showErrors(nextErrors: Errors, targetStep: Step) {
    setStep(targetStep);
    setErrors(nextErrors);

    requestAnimationFrame(() => {
      formRef.current
        ?.querySelector<HTMLInputElement>('[aria-invalid="true"]')
        ?.focus();
    });
  }

  function goNext() {
    const nextErrors =
      step === 0 ? validateTripDetails() : validatePreferences();

    if (Object.keys(nextErrors).length > 0) {
      showErrors(nextErrors, step);
      return;
    }

    changeStep(step === 0 ? 1 : 2);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (submitting) return;

    // Pressing Enter on an earlier step advances, rather than submitting.
    if (step !== 2) {
      goNext();
      return;
    }

    const tripErrors = validateTripDetails();

    if (Object.keys(tripErrors).length > 0) {
      showErrors(tripErrors, 0);
      return;
    }

    const preferenceErrors = validatePreferences();

    if (Object.keys(preferenceErrors).length > 0) {
      showErrors(preferenceErrors, 1);
      return;
    }

    const profile: TravelerProfile = {
      interests: { ...interests },
      pace,
      max_walk_minutes: Number(maxWalk),
      daily_active_hours: 8,
      day_start: dayStart,
      day_end: dayEnd,
      budget: {
        total: Number(budget),
        currency,
      },
      dietary: dietary
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean),
      accessibility: [],
      avoid: [],
      novelty_appetite: 0.3,
      feedback: {
        accepted: [],
        rejected: [],
      },
    };

    onSubmit({
      profile,
      destination: { name: destination.trim() },
      start_date: startDate,
      end_date: endDate,
    });
  }

  function errorMessage(field: string) {
    return errors[field] ? (
      <span id={`${field}-error`} className="form-error" role="alert">
        {errors[field]}
      </span>
    ) : null;
  }

  function errorAttributes(field: string) {
    return {
      "aria-invalid": Boolean(errors[field]),
      "aria-describedby": errors[field] ? `${field}-error` : undefined,
    };
  }

  return (
    <form
      ref={formRef}
      className="card preference-wizard"
      onSubmit={handleSubmit}
      noValidate
    >
      <h2>Plan a trip</h2>

      <ol className="wizard-steps" aria-label="Trip planning progress">
        {STEPS.map((label, index) => (
          <li
            key={label}
            className={index === step ? "wizard-step-current" : undefined}
            aria-current={index === step ? "step" : undefined}
          >
            <span aria-hidden="true">{index + 1}. </span>
            {label}
          </li>
        ))}
      </ol>

      <h3 ref={headingRef} tabIndex={-1}>
        {STEPS[step]}
      </h3>

      <fieldset className="wizard-fields" disabled={submitting}>
        <legend className="wizard-sr-only">{STEPS[step]} inputs</legend>

        {step === 0 && (
          <div className="row trip-dates">
            <label className="field">
              Destination
              <input
                value={destination}
                onChange={(event) => {
                  setDestination(event.target.value);
                  clearError("destination");
                }}
                {...errorAttributes("destination")}
              />
              {errorMessage("destination")}
            </label>

            <label className="field">
              Start date
              <input
                type="date"
                value={startDate}
                onChange={(event) => {
                  setStartDate(event.target.value);
                  clearError("startDate");
                  clearError("endDate");
                }}
                {...errorAttributes("startDate")}
              />
              {errorMessage("startDate")}
            </label>

            <label className="field">
              End date
              <input
                type="date"
                min={startDate || undefined}
                value={endDate}
                onChange={(event) => {
                  setEndDate(event.target.value);
                  clearError("endDate");
                }}
                {...errorAttributes("endDate")}
              />
              {errorMessage("endDate")}
            </label>
          </div>
        )}

        {step === 1 && (
          <>
            <h4>What do you care about?</h4>

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
                    onChange={(event) => {
                      const value = Number(event.target.value);

                      setInterests((previous) => ({
                        ...previous,
                        [key]: value,
                      }));
                    }}
                  />
                </label>
              ))}
            </div>

            <h4>Travel style</h4>

            <label className="slider">
              <span className="slider-label">
                Pace <em>{pace.toFixed(1)}</em> (0 relaxed → 1 packed)
              </span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.1}
                value={pace}
                onChange={(event) => setPace(Number(event.target.value))}
              />
            </label>

            <div className="travel-style-grid">
              <label className="field">
                Max walk between stops (min)
                <input
                  type="number"
                  min={0}
                  max={240}
                  value={maxWalk}
                  onChange={(event) => {
                    setMaxWalk(event.target.value);
                    clearError("maxWalk");
                  }}
                  {...errorAttributes("maxWalk")}
                />
                {errorMessage("maxWalk")}
              </label>

              <label className="field">
                Budget ({currency})
                <input
                  type="number"
                  min={0}
                  step="any"
                  value={budget}
                  onChange={(event) => {
                    setBudget(event.target.value);
                    clearError("budget");
                  }}
                  {...errorAttributes("budget")}
                />
                {errorMessage("budget")}
              </label>

              <label className="field">
                Day start
                <input
                  type="time"
                  value={dayStart}
                  onChange={(event) => {
                    setDayStart(event.target.value);
                    clearError("dayStart");
                    clearError("dayEnd");
                  }}
                  {...errorAttributes("dayStart")}
                />
                {errorMessage("dayStart")}
              </label>

              <label className="field">
                Day end
                <input
                  type="time"
                  value={dayEnd}
                  onChange={(event) => {
                    setDayEnd(event.target.value);
                    clearError("dayEnd");
                  }}
                  {...errorAttributes("dayEnd")}
                />
                {errorMessage("dayEnd")}
              </label>
            </div>

            <label className="field">
              Dietary preferences (comma-separated)
              <input
                value={dietary}
                onChange={(event) => setDietary(event.target.value)}
              />
            </label>
          </>
        )}

        {step === 2 && (
          <div className="wizard-review">
            <section aria-labelledby="review-trip-heading">
              <div className="wizard-review-heading">
                <h4 id="review-trip-heading">Trip details</h4>
                <button type="button" onClick={() => changeStep(0)}>
                  Edit trip details
                </button>
              </div>

              <dl>
                <dt>Destination</dt>
                <dd>{destination.trim()}</dd>

                <dt>Travel dates</dt>
                <dd>{startDate} → {endDate}</dd>
              </dl>
            </section>

            <section aria-labelledby="review-preferences-heading">
              <div className="wizard-review-heading">
                <h4 id="review-preferences-heading">Preferences</h4>
                <button type="button" onClick={() => changeStep(1)}>
                  Edit preferences
                </button>
              </div>

              <dl>
                <dt>Interests</dt>
                <dd>
                  {INTEREST_KEYS.map(
                    (key) => `${key}: ${(interests[key] ?? 0).toFixed(1)}`
                  ).join(" · ")}
                </dd>

                <dt>Pace</dt>
                <dd>{pace.toFixed(1)} (0 relaxed → 1 packed)</dd>

                <dt>Maximum walk between stops</dt>
                <dd>{maxWalk} minutes</dd>

                <dt>Budget</dt>
                <dd>{budget} {currency}</dd>

                <dt>Daily schedule</dt>
                <dd>{dayStart}–{dayEnd}</dd>

                <dt>Dietary preferences</dt>
                <dd>{dietary.trim() || "None specified"}</dd>
              </dl>
            </section>
          </div>
        )}

        <div className="wizard-actions">
          {step > 0 && (
            <button
              type="button"
              onClick={() => changeStep(step === 2 ? 1 : 0)}
            >
              Back
            </button>
          )}

          {step < 2 ? (
            <button type="button" onClick={goNext}>
              Next
            </button>
          ) : (
            <button type="submit">
              {submitting ? "Planning…" : "Plan my trip"}
            </button>
          )}
        </div>
      </fieldset>
    </form>
  );
}
