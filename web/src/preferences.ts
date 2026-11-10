// Plain-language choices for the Preferences step, and how they map onto the numbers the
// TravelerProfile contract expects (interest weights and pace are 0–1). Travelers pick
// "Love" or "Relaxed"; the backend still receives numbers, so no contract change.

import { INTEREST_KEYS } from "./interests";
import type { InterestKey } from "./interests";

export interface Choice {
  label: string;
  value: number;
}

export const INTEREST_LEVELS: Choice[] = [
  { label: "Skip", value: 0 },
  { label: "Some", value: 0.5 },
  { label: "Love", value: 1 },
];

export const PACE_OPTIONS: Array<Choice & { hint: string }> = [
  { label: "Relaxed", value: 0.2, hint: "Fewer stops, more time at each" },
  { label: "Balanced", value: 0.5, hint: "A steady day with breathing room" },
  { label: "Packed", value: 0.8, hint: "As much as the day allows" },
];

// Longest walk from one stop to the next, in minutes (TravelerProfile.max_walk_minutes).
// A hard limit for several travelers (PRODUCT.md), so it sits on the main Preferences step.
export const WALK_OPTIONS = [10, 20, 30, 45];

export const DEFAULT_INTERESTS: Record<InterestKey, number> = {
  food: 1,
  history: 1,
  art: 0.5,
  architecture: 0.5,
  nature: 0.5,
  nightlife: 0,
  shopping: 0,
};

export const DEFAULT_PACE = 0.5;

export const DIETARY_OPTIONS = [
  "vegetarian",
  "vegan",
  "halal",
  "kosher",
  "gluten-free",
  "nut allergy",
  "lactose-free",
];

const INTEREST_NAMES: Record<InterestKey, string> = {
  food: "Food",
  history: "History",
  art: "Art",
  architecture: "Architecture",
  nature: "Nature",
  nightlife: "Nightlife",
  shopping: "Shopping",
};

export function interestName(key: InterestKey): string {
  return INTEREST_NAMES[key];
}

/** The level a weight belongs to, so older 0–1 values still show a sensible choice. */
export function levelFor(weight: number): number {
  if (weight >= 0.75) return 1;
  if (weight >= 0.25) return 0.5;
  return 0;
}

export function paceLabel(pace: number): string {
  const closest = PACE_OPTIONS.reduce((best, option) =>
    Math.abs(option.value - pace) < Math.abs(best.value - pace) ? option : best,
  );
  return closest.label;
}

/** "Love: Food, History · Some: Art, Nature" for the Review step. */
export function describeInterests(interests: Record<string, number>): string {
  const groups = [...INTEREST_LEVELS]
    .reverse()
    .filter((level) => level.value > 0)
    .map((level) => {
      const names = INTEREST_KEYS.filter((key) => levelFor(interests[key] ?? 0) === level.value).map(
        interestName,
      );
      return names.length ? `${level.label}: ${names.join(", ")}` : "";
    })
    .filter(Boolean);
  return groups.join(" · ") || "Nothing selected";
}
