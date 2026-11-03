# Product

<!-- impeccable:product-schema 1 -->

This file records who Wanderwise is for and what it must do, for anyone (or any AI tool) making
design decisions. It is not the architecture: that lives in DESIGN.md. Statements marked
*(inferred)* were drawn from the repo rather than confirmed by the team; correct or confirm them.

## Platform

web

## Users

Travelers who have already chosen a city and a set of dates, and want a day-by-day plan they can
actually follow. The team's three Sprint 0 personas (`Arjun_Mehta.pdf`, `Sarah_Johnson.pdf`,
`Michael_Thompson.pdf`, labelled Persona 1–3) describe who we design for. Details and quotes
below are copied from those PDFs:

- **Budget-conscious student traveler (Arjun, 24).** Travels between semesters on a fixed budget.
  Researches for hours across blogs and maps, then still backtracks and overspends. Needs:
  budget-aware ranking, verified hours and costs, a walking limit.
  *"I want to explore the city without exceeding my budget or wasting time between places."*
- **Parent planning a family vacation (Sarah, 38, two kids aged 7 and 10).** Plans one big trip a
  year around different energy levels. Needs: family-friendly filters, meal and rest breaks, easy
  re-planning when the day runs late.
  *"I want my family to enjoy the trip without rushing, walking too much, or missing breaks."*
- **Traveler with limited mobility (Michael, 63).** Loves history and museums; a knee condition
  limits how far he can walk. Avoids booking trips because he can't tell in advance whether a
  plan is manageable. Needs: accessibility filters, shorter routes and rest time, honest
  confidence warnings.
  *"I need to know my itinerary is physically manageable before I begin the trip."*

The job shared by all three: turn "where, when, and what I care about" into a plan that fits real
constraints (money, walking, energy, opening hours), and trust it before the trip starts.

## Product Purpose

Wanderwise produces a day-by-day itinerary for any city that is **actually executable**: real
opening hours, real travel times between stops, real costs. The user can then change it (remove
places and re-plan today; natural-language edits are planned).

Success, for the user, is a plan they can follow without backtracking, overspending, or
exhausting themselves, and that tells them where its data is uncertain. *(inferred from the
README and personas)*

For the project, Wanderwise is the CS-691 team project (Team F2026-Team4). Its graded core and
technical-paper result is the trained learning-to-rank recommender, evaluated against baselines
(random, popularity, hand-coded scorer, LLM-as-recommender).

## Positioning

**The design is: a trained model ranks the places, a deterministic optimizer schedules them, and
a language model only handles language.** A language model is never the source of truth for
opening hours, travel times, prices, scores, or which places end up in the plan. This is the
claim a "just ask a chatbot for an itinerary" product cannot truthfully make, and the failure
mode the project exists to avoid.

**Status on `main` (early November 2026):** the deterministic optimizer is live
(`optimizer/scheduler.py`). Places are currently ranked by a rule-based scorer
(`optimizer/scoring.py`); the trained LightGBM ranker is being evaluated (open PRs #33, #34) but
is not yet wired into `/plan`. No language model runs in the product yet; the AI layer (Ollama)
is marked "Later" in the README. Interface copy should describe what is live, not the target.

Second differentiator: **confidence is carried end to end.** Places carry `known`, `inferred` or
`unknown` confidence for their opening hours and their cost. Today each itinerary stop shows its
hours confidence (verified, estimated, unverified), and the optimizer adds a warning when
scheduled places have unverified hours or prices. A per-stop cost label (`cost_confidence`) is in
flight in PR #32 and also needs the optimizer to copy the field into each stop.

## Operating Context

- The user names a destination; city data is fetched live from OpenStreetMap on the first
  request and cached. The first plan for a new city can take about a minute.
- The flow today: a three-step form (trip details, preferences, review) → itinerary shown one
  day at a time → remove places and re-plan.
- Planning happens before the trip, usually on a laptop *(inferred)*. Re-planning "on the fly when
  the day runs late" (Sarah) implies use on a phone during the trip too *(inferred)*, so the
  phone-width layout matters.
- Prices are in the destination's own currency; the budget is applied only when it is in that
  same currency (there is no currency conversion yet).
- The product is shown in sprint demos and presentations (see `Video DEMO.mp4` and the sprint
  slides in the repo root).

## Capabilities and Constraints

**Built:** live city fetch from OpenStreetMap; city suggestions while typing (Photon); interests
on seven fixed dimensions (food, history, art, architecture, nature, nightlife, shopping); pace;
maximum walk between stops; daily start and end time; budget with currency; dietary
preferences; day-by-day itinerary with times, travel time, cost, reason, and confidence labels;
match score; optimizer warnings; remove-and-re-plan.

**Planned, not built yet:** the trained ranker in the live plan (see Positioning);
natural-language edits; per-stop cost confidence labels (PR #32); map of each day (needs coordinates on
itinerary items, a contract change); accessibility filters (the profile has an `accessibility`
field, but the form always sends it empty); family-friendly filters; meal and rest breaks;
shareable trip link.

**Explicit non-goals** (from DESIGN.md): choosing the destination for the user; booking flights,
hotels or restaurants; collaborative filtering; native mobile apps; multi-city trips; user
accounts beyond what the demo needs.

**Open conflict, needs a team decision:** the Sprint 2 draft goal reportedly includes multi-city
itineraries, which DESIGN.md lists as a non-goal. (The Sprint 2 draft is not in the repo, so this
could not be checked here.) Either DESIGN.md takes multi-city into scope, or Sprint 2 drops it.
Until then, do not design for multi-city.

**Technical and team constraints:**
- The data shapes in `/contracts` (Place, TravelerProfile, Itinerary) are the source of truth
  and change only with whole-team agreement. The seven interest dimensions are defined in
  `contracts/categories.json`; the frontend's sliders use a hard-coded copy of the same seven
  in `web/src/interests.ts`, which must be kept in sync.
- `main` must always run; every change goes through a PR with green CI and one approval.
- Frontend: React + TypeScript + Vite, tested with vitest. Frontend files are owned by the
  Frontend lead (Siddharth).
- The browser must not call Nominatim (its usage policy forbids client-side autocomplete); city
  suggestions use Photon.

**Terminology:** "itinerary", "stop", "day", "re-plan", "match", and the confidence labels shown
to users: *verified* (known), *estimated* (inferred), *unverified* (unknown).

## Brand Commitments

- Name: **Wanderwise** (README, app, DESIGN.md). Some sprint files spell it "WanderWise"; the
  product itself uses "Wanderwise". *(Which spelling is canonical is undecided.)*
- Voice: plain and honest. The product admits uncertainty rather than hiding it ("where the
  data is thin, the system says so instead of pretending"). *(inferred from DESIGN.md and the
  current interface copy)*
- No logo or other brand assets exist in the repo.

## Evidence on Hand

- Three Sprint 0 personas: `Arjun_Mehta.pdf`, `Sarah_Johnson.pdf`, `Michael_Thompson.pdf`.
- Sprint presentations, user stories, test cases and burndown charts in the repo root,
  `docs/` and `documents/`.
- Spike results and the model card in `docs/` (data coverage, LLM reliability, routing,
  `model-card.md`).
- Sample data: `fixtures/lisbon.places.json`, `fixtures/sample.profile.json`.
- `Video DEMO.mp4`.

**Absent, and must not be invented:** real users, testimonials, usage numbers, reviews, press,
or ratings. OpenStreetMap has no user ratings and none are collected, so the product has no
ratings at all. The personas are design tools, not customers.

## Product Principles

1. **Executable over impressive.** A shorter plan that works beats a longer one that doesn't.
   Real hours, travel times and costs come first.
2. **Honest about uncertainty.** Show what is verified, estimated or unknown, and warn when a
   constraint (like the budget) could not be applied.
3. **The traveler's limits are hard limits.** Budget, walking distance, pace and energy shape
   the plan; they are not suggestions to trade away for more stops.
4. **Easy to change.** Removing a place and re-planning should be quick and safe, because days
   don't go to plan.
5. **The model ranks, the optimizer schedules, the language model only talks.** Interface copy
   must never imply that a language model planned the trip.

## Accessibility & Inclusion

- One of the three primary personas has limited mobility, so physical accessibility of the
  *plan* (walking limits, rest, honest accessibility data) is a product requirement, not an
  extra.
- Goal: the interface itself should meet WCAG 2.2 AA (keyboard use, screen-reader labels,
  contrast, reduced-motion support). *(inferred; no standard has been set by the team)* It does
  not fully meet it yet: the city search lacks combobox semantics and nests buttons inside its
  label, and the "unverified" badge text is about 4.4:1, just under the 4.5:1 minimum.
- Dietary needs (vegetarian, vegan, halal, kosher, gluten-free, nut allergy, lactose-free) are
  collected. Goal: the form should not assume any of them. *(inferred from the audit)* Today it
  starts with vegetarian selected.
