# LLM spike (AI) — fill in a NUMBER

**Question:** Can a local 8B-class model (via Ollama) reliably turn a paragraph into a valid
`TravelerProfile`?

Run `extract_profile` over ~20 hand-written traveler descriptions and fill this in.

| Model | Valid-output rate | p95 latency (s) | Notes |
|-------|------------------:|----------------:|-------|
| (e.g. llama3.1:8b) | | | |

**Decision this informs:** whether the local model is good enough for the demo, or whether we
need the provider abstraction to fall back to a hosted model for extraction.
