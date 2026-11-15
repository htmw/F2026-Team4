import { useState } from "react";

import { ApiError, postProfileFromText } from "./api";
import type { TravelerProfile } from "./types";

interface Props {
  // Called with the profile the backend extracted and the fields it filled with defaults.
  onProfile: (profile: TravelerProfile, defaultsUsed: string[]) => void;
}

// Friendly names for the fields the backend reports in `defaults_used`.
const FIELD_LABELS: Record<string, string> = {
  interests: "your interests",
  pace: "the pace",
  max_walk_minutes: "the walking limit",
  budget: "the budget",
  day_start: "the day start time",
  day_end: "the day end time",
  dietary: "dietary needs",
  novelty_appetite: "how adventurous to be",
};

function humanList(fields: string[]): string {
  const names = fields.map((field) => FIELD_LABELS[field] ?? field.replace(/_/g, " "));
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

function messageFor(err: unknown): string {
  if (err instanceof ApiError && err.status === 503) {
    return "The trip assistant isn't available right now — set your preferences below instead.";
  }
  if (err instanceof ApiError && err.status === 502) {
    return "Couldn't turn that into preferences — try rephrasing, or set them below.";
  }
  return err instanceof Error ? err.message : "Something went wrong — set your preferences below.";
}

// An optional free-text box: the traveler describes their trip, the backend's LLM turns it
// into a TravelerProfile, and we pre-fill the Preferences fields. Everything stays editable.
export function DescribeTrip({ onProfile }: Props) {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function fillFromText() {
    const trimmed = text.trim();
    if (!trimmed) {
      setNote(null);
      setError("Write a sentence or two about your trip first.");
      return;
    }
    setLoading(true);
    setError(null);
    setNote(null);
    try {
      const { profile, defaults_used } = await postProfileFromText(trimmed);
      onProfile(profile, defaults_used);
      setNote(
        defaults_used.length > 0
          ? `Set the preferences below. We guessed ${humanList(defaults_used)} — have a look.`
          : "Set the preferences below from your description — edit anything that's off.",
      );
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="group describe-trip">
      <label htmlFor="describe-trip-text" className="group-title">
        Describe your trip <span className="describe-trip-optional">(optional)</span>
      </label>
      <p className="field-hint">
        Tell us what you're into and we'll fill in the preferences below — for example: "I love food and
        history, hate long walks, about €1000 for three days."
      </p>
      <textarea
        id="describe-trip-text"
        className="describe-trip-input"
        rows={3}
        value={text}
        placeholder="I'm into…"
        onChange={(event) => {
          setText(event.target.value);
          setError(null);
        }}
        aria-describedby="describe-trip-status"
      />
      <div className="describe-trip-actions">
        <button
          type="button"
          className="button-secondary"
          onClick={fillFromText}
          disabled={loading}
        >
          {loading ? "Reading…" : "Fill from description"}
        </button>
      </div>
      <div id="describe-trip-status" aria-live="polite">
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
        {note && <p className="field-hint describe-trip-note">{note}</p>}
      </div>
    </div>
  );
}
