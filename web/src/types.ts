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
  name?: string;
  cost_confidence?: Confidence;
  start: string;
  end: string;
  // walk_minutes: walking in the move, including to and from the stop of a transit ride.
  travel_from_prev?: { minutes: number; mode: string; walk_minutes?: number };
  cost: number;
  // What the place is; "wikipedia" text is credited next to it.
  description?: string;
  description_source?: "wikipedia" | "openstreetmap";
  // The place's own website, when OpenStreetMap lists one ("Tickets" or "Website" link).
  website?: string;
  // When the place is open on the visit's day, as [open, close] pairs.
  open_hours?: [string, string][];
  reason: string;
  confidence: Confidence;
  // Not in the contract yet: where the place is, for the day map. No coordinates, no map.
  lat?: number;
  lon?: number;
}

export interface DayWeather {
  summary: string;
  rainy: boolean;
  rain_probability?: number | null;
  temp_max_c?: number | null;
  temp_min_c?: number | null;
}

export interface ItineraryDay {
  date: string;
  items: ItineraryItem[];
  // The forecast, when the trip is close enough (about 16 days) to have one.
  weather?: DayWeather;
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
