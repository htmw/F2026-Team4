# LLM spike (AI): free text to TravelerProfile

**Question:** Can a local 8B-class model (via Ollama) reliably turn a paragraph into a
valid `TravelerProfile`?

Generated 2026-11-02 by `python -m ai.benchmark` on Darwin arm64. Each description gets up to
3 attempts; invalid replies are sent back to the model with the problems
listed. Latency is the whole extraction including retries, after one warm-up call that
loads the model.

## Answer

| Model | Valid-output rate | p95 latency (s) | Notes |
|-------|------------------:|----------------:|-------|
| llama3 | 100% (20/20) | 22.4 | median 14.9 s, 20/20 valid on the first try |

## Was the profile right, not just valid?

Each description lists what a correct profile must show, for example "food high" or
"currency JPY" (`fixtures/traveler-descriptions.json`).

- Checks passed: 74/78 (95%)
- Descriptions with every check passed: 16/20
- Mean attempts per description: 1.00

| Description | Valid | Attempts | Seconds | Checks | Missed |
|---|---|---:|---:|---:|---|
| vegetarian-foodies | yes | 1 | 17.5 | 5/5 |  |
| history-teacher | yes | 1 | 21.9 | 4/5 | pace packed |
| art-lover | yes | 1 | 14.6 | 3/3 |  |
| bachelor-party | yes | 1 | 33.5 | 2/3 | start >= 11:00 |
| wheelchair-architecture | yes | 1 | 19.5 | 4/4 |  |
| student-backpacker | yes | 1 | 16.8 | 5/6 | no invented diet |
| family-young-kids | yes | 1 | 14.0 | 4/4 |  |
| shopper | yes | 1 | 8.9 | 2/2 |  |
| coeliac-slow-mornings | yes | 1 | 15.6 | 2/2 |  |
| architecture-photographer | yes | 1 | 10.7 | 4/4 |  |
| halal-history | yes | 1 | 10.2 | 4/4 |  |
| no-churches | yes | 1 | 14.2 | 5/5 |  |
| terse-food | yes | 1 | 14.2 | 2/2 |  |
| vague-relaxing | yes | 1 | 13.2 | 2/2 |  |
| luxury-anniversary | yes | 1 | 16.3 | 6/6 |  |
| spanish-couple | yes | 1 | 15.3 | 6/6 |  |
| walks-with-a-cane | yes | 1 | 15.4 | 4/4 |  |
| vegan-techno | yes | 1 | 13.5 | 3/4 | start >= 10:00 |
| hiker-nut-allergy | yes | 1 | 11.6 | 4/4 |  |
| yen-budget | yes | 1 | 15.6 | 3/3 |  |

## Decision this informs

Whether the local model is good enough for the demo, or whether extraction should fall
back to a hosted model through the provider abstraction in `ai/llm.py`. Either way the
traveler reviews the extracted profile in the form before planning, and the API lists
which fields were not mentioned and filled with defaults.
