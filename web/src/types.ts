// TypeScript mirror of the /contracts JSON Schemas. Keep these in sync with the schemas —
// they are the same three shapes the whole team codes against.

export type Confidence = "known" | "inferred" | "unknown";

export interface TravelerProfile {
  interests: Record<string, number>;
  pace: number;
  max_walk_minutes: number;
  daily_active_hours?: number;
  day_start: string;
  day_end: string;
  budget: { total: number; currency: string };
  dietary: string[];
  accessibility: string[];
  avoid: string[];
  novelty_appetite: number;
  feedback: { accepted: string[]; rejected: string[] };
}

export interface Destination {
  name: string;
  country?: string;
  lat?: number;
  lon?: number;
}

export interface ItineraryItem {
  place_id: string;
  start: string;
  end: string;
  travel_from_prev?: { minutes: number; mode: string };
  cost: number;
  reason: string;
  confidence: Confidence;
}

export interface ItineraryDay {
  date: string;
  items: ItineraryItem[];
}

export interface Itinerary {
  trip_id: string;
  destination: { name: string; country?: string; lat: number; lon: number };
  start_date: string;
  end_date: string;
  days: ItineraryDay[];
  totals: { cost: number; currency: string; walking_minutes: number };
  warnings?: string[];
  score?: number;
}

export interface PlanRequest {
  profile: TravelerProfile;
  destination: Destination;
  start_date: string;
  end_date: string;
}
