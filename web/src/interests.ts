// The 7 interest dimensions. Mirrors `interests` in /contracts/categories.json.
// Later, the Frontend owner can fetch these from the API instead of hardcoding.
export const INTEREST_KEYS = [
  "food",
  "history",
  "art",
  "architecture",
  "nature",
  "nightlife",
  "shopping",
] as const;

export type InterestKey = (typeof INTEREST_KEYS)[number];
