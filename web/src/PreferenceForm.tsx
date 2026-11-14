import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import { CitySearch } from "./CitySearch";
import type { CitySuggestion } from "./CitySearch";
import { currencyLabel, currencyOptions } from "./currency";
import { formatDateRange, formatMoney, formatTime } from "./format";
import { ChevronDown } from "./icons";
import { INTEREST_KEYS } from "./interests";
import {
  DEFAULT_INTERESTS,
  DEFAULT_PACE,
  DIETARY_OPTIONS,
  INTEREST_LEVELS,
  PACE_OPTIONS,
  WALK_OPTIONS,
  describeInterests,
  interestName,
  levelFor,
  paceLabel,
} from "./preferences";
import type { PlanRequest, TravelerProfile } from "./types";

const STEPS = ["Trip details", "Preferences", "Review"] as const;

type Step = 0 | 1 | 2;
type Errors = Record<string, string>;

// Fields that live behind "More options" on the Preferences step. If one of them has an
// error, the section opens so the error is never hidden.
const MORE_OPTION_FIELDS = ["dayStart", "dayEnd"];

interface Props {
  onSubmit: (req: PlanRequest) => void;
  submitting: boolean;
  // A destination problem reported by the server ("'japan' is a country, not a city").
  // `seq` changes on every new error, so the same message twice still reopens the field.
  destinationError?: { message: string; seq: number } | null;
}

export function PreferenceForm({ onSubmit, submitting, destinationError }: Props) {
  const [step, setStep] = useState<Step>(0);
  const [errors, setErrors] = useState<Errors>({});

  // State stays here so switching steps preserves all inputs.
  const [destination, setDestination] = useState("Lisbon");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [interests, setInterests] = useState<Record<string, number>>({ ...DEFAULT_INTERESTS });
  const [pace, setPace] = useState(DEFAULT_PACE);
  const [maxWalk, setMaxWalk] = useState("20");
  const [budget, setBudget] = useState("1200");
  const [dayStart, setDayStart] = useState("09:30");
  const [dayEnd, setDayEnd] = useState("22:00");
  // No diet is assumed: travelers opt in to what applies to them.
  const [dietary, setDietary] = useState<string[]>([]);
  const [moreOpen, setMoreOpen] = useState(false);

  // The optimizer applies the budget only when it is in the local currency, so choosing a
  // suggested city switches the budget to that country's currency. The user can still change it.
  const [currency, setCurrency] = useState("EUR");
  // Local currency of the chosen city; unknown when the name was typed by hand.
  const [localCurrency, setLocalCurrency] = useState<string | undefined>("EUR");
  // Set when choosing a city switched the currency and cleared the amount, so the hint can
  // ask for a new amount. An amount typed for one currency is meaningless in another
  // (1200 EUR is not 1200 JPY), so it is never carried across.
  const [budgetReset, setBudgetReset] = useState<string | null>(null);

  // Local "today" in YYYY-MM-DD form, used to block past dates.
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const headingRef = useRef<HTMLHeadingElement>(null);
  const formRef = useRef<HTMLFormElement>(null);

  // Show a server-side destination problem on the Destination field itself.
  useEffect(() => {
    if (!destinationError) return;
    setStep(0);
    setErrors({ destination: destinationError.message });
    focusFirstInvalid();
  }, [destinationError]);

  function focusFirstInvalid() {
    requestAnimationFrame(() => {
      formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"], [data-error-anchor]')?.focus();
    });
  }

  function selectCity({ value, currency: cityCurrency }: CitySuggestion) {
    setDestination(value);
    setLocalCurrency(cityCurrency);
    if (cityCurrency && cityCurrency !== currency) {
      setCurrency(cityCurrency);
      setBudget("");
      setBudgetReset(cityCurrency);
    }
    clearError("destination");
  }

  function changeStep(nextStep: Step) {
    setStep(nextStep);
    setErrors({});
    requestAnimationFrame(() => headingRef.current?.focus());
  }

  function clearError(field: string) {
    setErrors((previous) => {
      if (!(field in previous)) return previous;
      const next = { ...previous };
      delete next[field];
      return next;
    });
  }

  function toggleDietary(option: string) {
    setDietary((previous) =>
      previous.includes(option) ? previous.filter((item) => item !== option) : [...previous, option],
    );
  }

  function validateTripDetails(): Errors {
    const next: Errors = {};
    if (!destination.trim()) next.destination = "Enter a city to plan a trip to.";
    if (!startDate) next.startDate = "Choose a start date.";
    else if (startDate < today) next.startDate = "The start date can't be in the past.";
    if (!endDate) next.endDate = "Choose an end date.";
    else if (startDate && endDate < startDate) next.endDate = "The end date can't be before the start date.";
    return next;
  }

  function validatePreferences(): Errors {
    const next: Errors = {};
    const walkingMinutes = Number(maxWalk);
    const totalBudget = Number(budget);
    if (!maxWalk.trim() || !Number.isFinite(walkingMinutes) || walkingMinutes < 0 || walkingMinutes > 240) {
      next.maxWalk = "Enter a walking limit between 0 and 240 minutes.";
    }
    if (!budget.trim() || !Number.isFinite(totalBudget) || totalBudget < 0) {
      next.budget = `Enter a budget in ${currency} (0 or more).`;
    }
    if (!dayStart) next.dayStart = "Choose when your day starts.";
    if (!dayEnd) next.dayEnd = "Choose when your day ends.";
    else if (dayStart && dayEnd <= dayStart) next.dayEnd = "The day has to end after it starts.";
    if (INTEREST_KEYS.every((key) => (interests[key] ?? 0) === 0)) {
      next.interests = "Choose Some or Love for at least one interest, so we know what to look for.";
    }
    return next;
  }

  function showErrors(nextErrors: Errors, targetStep: Step) {
    setStep(targetStep);
    setErrors(nextErrors);
    if (MORE_OPTION_FIELDS.some((field) => field in nextErrors)) setMoreOpen(true);
    focusFirstInvalid();
  }

  // Every step's primary button is a submit button, so Enter in any field moves the wizard
  // forward; the final step plans the trip.
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;

    if (step !== 2) {
      const nextErrors = step === 0 ? validateTripDetails() : validatePreferences();
      if (Object.keys(nextErrors).length > 0) {
        showErrors(nextErrors, step);
        return;
      }
      changeStep(step === 0 ? 1 : 2);
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
      budget: { total: Number(budget), currency },
      dietary,
      accessibility: [],
      avoid: [],
      novelty_appetite: 0.3,
      feedback: { accepted: [], rejected: [] },
    };

    onSubmit({
      profile,
      destination: { name: destination.trim() },
      start_date: startDate,
      end_date: endDate,
    });
  }

  function fieldError(field: string) {
    return errors[field] ? (
      <p id={`${field}-error`} className="field-error" role="alert">
        {errors[field]}
      </p>
    ) : null;
  }

  function errorAttributes(field: string, extraDescribedBy?: string) {
    const ids = [errors[field] ? `${field}-error` : "", extraDescribedBy ?? ""].filter(Boolean).join(" ");
    return {
      "aria-invalid": Boolean(errors[field]),
      "aria-describedby": ids || undefined,
    };
  }

  function budgetHint(): ReactNode {
    const city = destination.trim();
    if (budgetReset && budgetReset === currency && !budget.trim()) {
      return (
        <p className="field-hint" id="budget-hint">
          Prices in {city} are in {currency}, so the budget is now in {currency}. Enter an amount in{" "}
          {currency}.
        </p>
      );
    }
    if (localCurrency && localCurrency !== currency) {
      return (
        <p className="field-hint field-hint-warn" id="budget-hint">
          Prices in {city} are in {localCurrency}. A budget in {currency} can't be applied there yet.
        </p>
      );
    }
    if (!localCurrency && city) {
      return (
        <p className="field-hint" id="budget-hint">
          The budget only applies in the destination's own currency. Pick your city from the suggestions
          to set it automatically, or choose it here.
        </p>
      );
    }
    return null;
  }

  const hint = budgetHint();
  const moreSummary = [
    `${formatTime(dayStart)} – ${formatTime(dayEnd)}`,
    dietary.length ? dietary.join(", ") : "no dietary needs",
  ].join(" · ");

  return (
    <form
      ref={formRef}
      id="plan-form"
      className="panel plan-form"
      onSubmit={handleSubmit}
      noValidate
      aria-labelledby="plan-form-title"
    >
      <h2 id="plan-form-title" className="panel-title">
        Plan a trip
      </h2>

      <ol className="steps" aria-label="Progress">
        {STEPS.map((label, index) => {
          const state = index === step ? "current" : index < step ? "done" : "todo";
          return (
            <li key={label} className={`step step-${state}`} aria-current={index === step ? "step" : undefined}>
              <span className="step-number" aria-hidden="true">
                {index + 1}
              </span>
              {index === step ? (
                <h3 ref={headingRef} tabIndex={-1} className="step-title">
                  {label}
                </h3>
              ) : index < step ? (
                <button type="button" className="step-link" onClick={() => changeStep(index as Step)}>
                  {label}
                </button>
              ) : (
                <span className="step-label">{label}</span>
              )}
            </li>
          );
        })}
      </ol>

      <fieldset className="wizard-fields" disabled={submitting}>
        <legend className="visually-hidden">{STEPS[step]}</legend>

        {step === 0 && (
          <div className="trip-fields">
            <CitySearch
              value={destination}
              onType={(text) => {
                setDestination(text);
                setLocalCurrency(undefined);
                clearError("destination");
              }}
              onSelect={selectCity}
              error={errors.destination}
            />

            <div className="field">
              <label htmlFor="start-date">Start date</label>
              <input
                id="start-date"
                type="date"
                min={today}
                value={startDate}
                onChange={(event) => {
                  setStartDate(event.target.value);
                  clearError("startDate");
                  clearError("endDate");
                }}
                {...errorAttributes("startDate")}
              />
              {fieldError("startDate")}
            </div>

            <div className="field">
              <label htmlFor="end-date">End date</label>
              <input
                id="end-date"
                type="date"
                min={startDate || today}
                value={endDate}
                onChange={(event) => {
                  setEndDate(event.target.value);
                  clearError("endDate");
                }}
                {...errorAttributes("endDate")}
              />
              {fieldError("endDate")}
            </div>
          </div>
        )}

        {step === 1 && (
          <>
            <fieldset className="group">
              <legend className="group-title">What do you want to see?</legend>
              <div className="interest-list">
                {INTEREST_KEYS.map((key) => (
                  <fieldset key={key} className="interest-row">
                    <legend className="interest-name">{interestName(key)}</legend>
                    <div className="segmented">
                      {INTEREST_LEVELS.map((level) => (
                        <label key={level.label} className="segment">
                          <input
                            type="radio"
                            name={`interest-${key}`}
                            value={level.value}
                            checked={levelFor(interests[key] ?? 0) === level.value}
                            onChange={() => {
                              setInterests((previous) => ({ ...previous, [key]: level.value }));
                              if (level.value > 0) clearError("interests");
                            }}
                          />
                          <span>{level.label}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                ))}
              </div>
              {errors.interests && (
                <p id="interests-error" className="field-error" role="alert" tabIndex={-1} data-error-anchor>
                  {errors.interests}
                </p>
              )}
            </fieldset>

            <fieldset className="group">
              <legend className="group-title">Pace</legend>
              <div className="segmented segmented-wide">
                {PACE_OPTIONS.map((option) => (
                  <label key={option.label} className="segment">
                    <input
                      type="radio"
                      name="pace"
                      value={option.value}
                      checked={paceLabel(pace) === option.label}
                      onChange={() => setPace(option.value)}
                    />
                    <span>{option.label}</span>
                  </label>
                ))}
              </div>
              <p className="field-hint">{PACE_OPTIONS.find((o) => o.label === paceLabel(pace))?.hint}</p>
            </fieldset>

            <fieldset className="group">
              <legend className="group-title">Longest walk between stops</legend>
              <div className="segmented segmented-wide">
                {WALK_OPTIONS.map((minutes) => (
                  <label key={minutes} className="segment">
                    <input
                      type="radio"
                      name="max-walk"
                      value={minutes}
                      checked={Number(maxWalk) === minutes}
                      onChange={() => {
                        setMaxWalk(String(minutes));
                        clearError("maxWalk");
                      }}
                    />
                    <span>{minutes} min</span>
                  </label>
                ))}
              </div>
              <p className="field-hint">The plan tells you if any walk between two stops is longer than this.</p>
              {fieldError("maxWalk")}
            </fieldset>

            <div className="group">
              <div className="field budget-field">
                <label htmlFor="budget-amount" className="group-title">
                  Budget for the whole trip
                </label>
                <div className="budget-inputs">
                  <input
                    id="budget-amount"
                    type="number"
                    inputMode="decimal"
                    min={0}
                    step="any"
                    value={budget}
                    onChange={(event) => {
                      setBudget(event.target.value);
                      setBudgetReset(null);
                      clearError("budget");
                    }}
                    {...errorAttributes("budget", hint ? "budget-hint" : undefined)}
                  />
                  <select
                    aria-label="Budget currency"
                    value={currency}
                    onChange={(event) => {
                      setCurrency(event.target.value);
                      setBudgetReset(null);
                    }}
                  >
                    {currencyOptions(currency).map((code) => (
                      <option key={code} value={code}>
                        {currencyLabel(code)}
                      </option>
                    ))}
                  </select>
                </div>
                {hint}
                {fieldError("budget")}
              </div>
            </div>

            <div className="group more-options">
              <button
                type="button"
                className="disclosure"
                aria-expanded={moreOpen}
                aria-controls="more-options"
                onClick={() => setMoreOpen((open) => !open)}
              >
                <ChevronDown className={moreOpen ? "is-open" : undefined} />
                <span>
                  More options
                  {!moreOpen && <span className="disclosure-summary">{moreSummary}</span>}
                </span>
              </button>

              <div id="more-options" hidden={!moreOpen} className="more-options-body">
                <div className="time-pair">
                  <div className="field">
                    <label htmlFor="day-start">Start each day at</label>
                    <input
                      id="day-start"
                      type="time"
                      value={dayStart}
                      onChange={(event) => {
                        setDayStart(event.target.value);
                        clearError("dayStart");
                        clearError("dayEnd");
                      }}
                      {...errorAttributes("dayStart")}
                    />
                    {fieldError("dayStart")}
                  </div>
                  <div className="field">
                    <label htmlFor="day-end">End each day at</label>
                    <input
                      id="day-end"
                      type="time"
                      value={dayEnd}
                      onChange={(event) => {
                        setDayEnd(event.target.value);
                        clearError("dayEnd");
                      }}
                      {...errorAttributes("dayEnd")}
                    />
                    {fieldError("dayEnd")}
                  </div>
                </div>

                <fieldset className="field">
                  <legend>Dietary needs</legend>
                  <div className="chips">
                    {DIETARY_OPTIONS.map((option) => (
                      <label key={option} className="chip">
                        <input
                          type="checkbox"
                          checked={dietary.includes(option)}
                          onChange={() => toggleDietary(option)}
                        />
                        <span>{option}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              </div>
            </div>
          </>
        )}

        {step === 2 && (
          <div className="review">
            <section aria-labelledby="review-trip">
              <div className="review-heading">
                <h4 id="review-trip">Trip</h4>
                <button type="button" className="button-quiet" onClick={() => changeStep(0)}>
                  Edit
                </button>
              </div>
              <dl>
                <dt>Destination</dt>
                <dd>{destination.trim()}</dd>
                <dt>Dates</dt>
                <dd>{formatDateRange(startDate, endDate)}</dd>
              </dl>
            </section>

            <section aria-labelledby="review-preferences">
              <div className="review-heading">
                <h4 id="review-preferences">Preferences</h4>
                <button type="button" className="button-quiet" onClick={() => changeStep(1)}>
                  Edit
                </button>
              </div>
              <dl>
                <dt>Interests</dt>
                <dd>{describeInterests(interests)}</dd>
                <dt>Pace</dt>
                <dd>{paceLabel(pace)}</dd>
                <dt>Budget</dt>
                <dd>{formatMoney(Number(budget), currency)}</dd>
                <dt>Longest walk</dt>
                <dd>{maxWalk} minutes between stops</dd>
                <dt>Daily hours</dt>
                <dd>
                  {formatTime(dayStart)} – {formatTime(dayEnd)}
                </dd>
                <dt>Dietary needs</dt>
                <dd>{dietary.join(", ") || "None"}</dd>
              </dl>
            </section>
          </div>
        )}

        <div className="wizard-actions">
          {step > 0 && (
            <button type="button" className="button-secondary" onClick={() => changeStep((step - 1) as Step)}>
              Back
            </button>
          )}
          {/* Different keys, so React makes a new button for the final step instead of reusing
              the clicked one mid-click (which once submitted the form straight from
              Preferences, skipping Review). */}
          {step < 2 ? (
            <button key="next" type="submit" className="button-primary">
              Next
            </button>
          ) : (
            <button key="plan" type="submit" className="button-primary">
              {submitting ? "Planning…" : "Plan my trip"}
            </button>
          )}
        </div>
      </fieldset>
    </form>
  );
}
