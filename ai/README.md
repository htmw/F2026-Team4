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

## Run it
```bash
ollama pull llama3          # once
ollama serve                # leave running
make llm-spike              # 20 descriptions -> docs/llm-spike.md
```
From code: `extract_profile(text, get_llm())` returns an `ExtractionResult` with the
`profile`, the `defaults_used` (fields the traveler didn't mention) and the `attempts`.
Over HTTP: `POST /profile/from-text` with `{"text": "..."}`.

| File | What it does |
|------|--------------|
| [`llm.py`](llm.py) | the `LLM` interface, the Ollama provider, `get_llm()` from env vars |
| [`profile.py`](profile.py) | `extract_profile`: prompt, schema, defaults, validation, retries |
| [`benchmark.py`](benchmark.py) | the LLM spike over `fixtures/traveler-descriptions.json` |

Tests use a scripted fake model (`ai/tests/fakes.py`), so CI never needs Ollama.

## Rules
- Keep the model behind an abstraction. No provider names leak into the rest of the code.
- Validate every LLM output against the contract before it enters the system.
