# /ai — Traveler + Adaptation language layer (AI, 1 person)

**You own** the natural-language edges of the system — and nothing in the planning path.
The LLM turns messy human text into clean structured data, and clean decisions back into
human-readable sentences. It is never the source of truth for hours, prices, or scores.

## Contract boundary
- `extract_profile(text) -> TravelerProfile` — valid against
  [`/contracts/traveler-profile.schema.json`](../contracts/traveler-profile.schema.json),
  with retry on invalid output.
- Later: parse a natural-language edit ("more nightlife", "drop the hike") into a structured
  change the `/api` re-optimizer can apply; and write the `reason` explanations for itinerary items.

## Sprint-1 deliverable
- A **provider-agnostic** LLM interface with an **Ollama** implementation behind it. The app must be able to swap local → hosted model without rewriting callers.
- The **LLM spike** number in [`/docs/llm-spike.md`](../docs/llm-spike.md): over ~20
  hand-written traveler descriptions, what's the valid-output rate and p95 latency for a
  local 8B-class model?

## Rules
- Keep the model behind an abstraction. No provider names leak into the rest of the code.
- Validate every LLM output against the contract before it enters the system.
