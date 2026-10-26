diff --git a/api/main.py b/api/main.py
index 4d95cca..a79dc0a 100644
--- a/api/main.py
+++ b/api/main.py
@@ -8,8 +8,9 @@ Endpoints:
 Every incoming profile and every outgoing itinerary is validated against the contracts,
 so the moment any component drifts from the agreed shapes, we find out here.
 
-This is the seam the Optimizer team plugs into: swap `plan_itinerary` for the
-real `/optimizer` schedule() and nothing else in the system needs to change.
+Planning goes through `optimizer.scheduler.plan_itinerary`, which respects opening
+hours, travel time, budget and walking limits. `api/scheduler_stub.py` is kept as the
+original baseline.
 """
 
 from __future__ import annotations
@@ -24,9 +25,9 @@ from fastapi.middleware.cors import CORSMiddleware
 from pydantic import BaseModel
 
 from api.contracts import validate
-from api.scheduler_stub import plan_itinerary
 from api.trips import TripStore
 from ingest.catalog import CityFetchFailed, CityNotAvailable
+from optimizer.scheduler import plan_itinerary
 
 app = FastAPI(
     title="Wanderwise Travel Planning API",
@@ -157,7 +158,7 @@ def give_feedback(trip_id: str, feedback: Feedback) -> dict[str, Any]:
     """Record accepted/rejected places on the trip's profile, then re-plan the trip.
 
     Rejected places are left out of the new plan. Accepted places are only recorded for
-    now; the stub scheduler doesn't use them.
+    now; the scheduler does not use them yet.
     """
     both = set(feedback.accepted) & set(feedback.rejected)
     if both:
@@ -171,8 +172,8 @@ def give_feedback(trip_id: str, feedback: Feedback) -> dict[str, Any]:
     profile = request["profile"]
     profile["feedback"] = _merge_feedback(profile.get("feedback", {}), feedback)
 
-    # TODO(optimizer): waiting for re-optimization of only the affected days, keeping the
-    # rest of the trip as it was. Until then the whole trip is re-planned from scratch.
+    # TODO(optimizer, Sprint 2): re-optimize only the affected days, keeping the rest
+    # of the trip as it was. Until then the whole trip is re-planned from scratch.
     itinerary = _build_itinerary(request, trip_id=trip_id)
     store.save(trip_id, request, itinerary)
     return itinerary
diff --git a/optimizer/scheduler.py b/optimizer/scheduler.py
index 2bacf52..f31f3ec 100644
--- a/optimizer/scheduler.py
+++ b/optimizer/scheduler.py
@@ -4,6 +4,8 @@
 from __future__ import annotations
 
 import uuid
+from collections import Counter
+from collections.abc import Callable
 from typing import Any
 
 from optimizer.constraints import (
@@ -14,19 +16,69 @@ from optimizer.constraints import (
     to_hhmm,
     to_minutes,
 )
-from optimizer.scoring import recommendation_reason, score
+from optimizer.scoring import matched_interests, recommendation_reason, score
 from optimizer.travel import travel_between
 
+# Known opening hours are a hard constraint (checked in available_visit).
+# Inferred or unknown hours are allowed, but a place with verified hours is
+# preferred over an otherwise equal place whose hours are only a guess.
+HOURS_PENALTY = {"known": 0.0, "inferred": 0.1, "unknown": 0.2}
+
+# Each earlier stop today that served the same top interest lowers a place's utility,
+# so one interest does not fill a whole day (e.g. three food stops before noon).
+REPEAT_PENALTY = 0.15
+
+# Only the best-scoring places are considered for scheduling. A city can have thousands of
+# places; no trip needs more than this, and it keeps the travel matrix small (300 places
+# = about 90,000 legs).
+MAX_CANDIDATES = 300
+
+TravelMatrix = dict | Callable[[list[dict[str, Any]]], dict]
+
+
+def _shortlist(
+    candidates: list[dict[str, Any]],
+    quality_of: dict[str, float],
+    top_interest_of: dict[str, str],
+    limit: int,
+) -> list[dict[str, Any]]:
+    """The best `limit` places, taken in turn from each interest the traveler has.
+
+    A plain top-N by score can be all one kind: a city has thousands of restaurants, so a
+    food lover's top 300 would hold no sights at all and every day would be meals.
+    """
+    by_interest: dict[str, list[dict[str, Any]]] = {}
+    for place in sorted(candidates, key=lambda p: quality_of[p["id"]], reverse=True):
+        by_interest.setdefault(top_interest_of[place["id"]], []).append(place)
+
+    picked: list[dict[str, Any]] = []
+    queues = list(by_interest.values())
+    while queues and len(picked) < limit:
+        for queue in queues:
+            if queue and len(picked) < limit:
+                picked.append(queue.pop(0))
+        queues = [queue for queue in queues if queue]
+
+    picked.sort(key=lambda place: quality_of[place["id"]], reverse=True)
+    return picked
+
 
 def schedule(
     places: list[dict[str, Any]],
     profile: dict[str, Any],
     dates: list[str],
-    travel_matrix: dict | None = None,
+    travel_matrix: TravelMatrix | None = None,
     category_map: dict[str, list[str]] | None = None,
     destination: dict[str, Any] | None = None,
+    trip_id: str | None = None,
 ) -> dict[str, Any]:
-    """Produce an itinerary matching the existing JSON contract."""
+    """Produce an itinerary matching the existing JSON contract.
+
+    `travel_matrix` is either a ready {(from_id, to_id): {"minutes", "mode"}} dict, or a
+    function that builds one for the candidate places (the Data team's travel_legs).
+    Without one, travel times are estimated from straight-line distance.
+    Pass `trip_id` when re-planning an existing trip so it keeps its id.
+    """
 
     category_map = category_map or {}
     destination = destination or {
@@ -54,17 +106,57 @@ def schedule(
     )
 
     budget = float(profile["budget"]["total"])
-    currency = profile["budget"]["currency"]
+    budget_currency = profile["budget"]["currency"]
+
+    # Prices are in the city's own currency (INR in an Indian city), whatever currency the
+    # budget was typed in. There is no exchange-rate source, so never convert silently.
+    price_currencies = Counter(place["cost"]["currency"] for place in places)
+    currency = (
+        price_currencies.most_common(1)[0][0] if price_currencies else budget_currency
+    )
+    budget_applies = budget_currency == currency
+    if not budget_applies:
+        budget = float("inf")
     walking_limit = int(profile["max_walk_minutes"])
     stop_limit = max_stops(float(profile["pace"]))
+    rejected = set(profile.get("feedback", {}).get("rejected", []))
+
+    # Score every place once. score() already returns 0 for avoided places and
+    # for places that match none of the traveler's interests.
+    quality_of: dict[str, float] = {}
+    skipped_currency = 0
+    candidates: list[dict[str, Any]] = []
+
+    for place in places:
+        if place["id"] in rejected:
+            continue
+
+        # A stray price in another currency cannot be added to the trip total.
+        if place["cost"]["currency"] != currency:
+            skipped_currency += 1
+            continue
+
+        quality = score(place, profile, category_map)
+        if quality <= 0:
+            continue
+
+        quality_of[place["id"]] = quality
+        candidates.append(place)
+
+    # The interest each place serves best, used to keep days varied.
+    interest_weights = profile.get("interests", {})
+    top_interest_of = {
+        place["id"]: max(
+            matched_interests(place, category_map),
+            key=lambda name: interest_weights.get(name, 0.0),
+        )
+        for place in candidates
+    }
 
-    ranked = sorted(
-        places,
-        key=lambda place: score(
-            place, profile, category_map
-        ),
-        reverse=True,
-    )
+    candidates = _shortlist(candidates, quality_of, top_interest_of, MAX_CANDIDATES)
+
+    if callable(travel_matrix):
+        travel_matrix = travel_matrix(candidates)
 
     used: set[str] = set()
     days_out: list[dict[str, Any]] = []
@@ -81,37 +173,17 @@ def schedule(
         previous = None
         active_used = 0
         items = []
+        interests_today: dict[str, int] = {}
 
         while len(items) < stop_limit:
             options = []
 
-            for place in ranked:
+            for place in candidates:
                 if place["id"] in used:
                     continue
 
-                quality = score(
-                    place, profile, category_map
-                )
-
-                # Exclude explicitly avoided attractions.
-                if place["id"] in profile.get("avoid", []):
-                    continue
-
-                if set(place["categories"]) & set(
-                    profile.get("avoid", [])
-                ):
-                    continue
-
-                if quality <= 0:
-                    continue
-
-                cost_info = place["cost"]
-
-                # Do not silently convert currencies.
-                if cost_info["currency"] != currency:
-                    continue
-
-                cost = float(cost_info["amount"])
+                quality = quality_of[place["id"]]
+                cost = float(place["cost"]["amount"])
 
                 if not budget_allows(
                     budget - total_cost, cost
@@ -148,10 +220,14 @@ def schedule(
 
                 start, confidence = visit
 
-                # Prefer high quality, shorter transit and less waiting.
+                # Prefer high quality, verified hours, variety, shorter transit and
+                # less waiting.
                 waiting = start - (cursor + travel)
+                repeats = interests_today.get(top_interest_of[place["id"]], 0)
                 utility = (
                     quality
+                    - REPEAT_PENALTY * repeats
+                    - HOURS_PENALTY.get(confidence, HOURS_PENALTY["unknown"])
                     - 0.0005 * travel
                     - 0.0002 * waiting
                 )
@@ -189,6 +265,7 @@ def schedule(
 
             items.append({
                 "place_id": place["id"],
+                "name": place["name"],
                 "start": to_hhmm(start),
                 "end": to_hhmm(start + duration),
                 "travel_from_prev": {
@@ -203,6 +280,8 @@ def schedule(
             })
 
             used.add(place["id"])
+            top = top_interest_of[place["id"]]
+            interests_today[top] = interests_today.get(top, 0) + 1
             previous = place
             cursor = start + duration
             active_used += travel + duration
@@ -218,9 +297,8 @@ def schedule(
             if confidence != "known":
                 unknown_hours += 1
 
-            if cost_info := place.get("cost"):
-                if cost_info.get("confidence") != "known":
-                    unknown_costs += 1
+            if place["cost"].get("confidence") != "known":
+                unknown_costs += 1
 
         days_out.append({
             "date": day,
@@ -247,6 +325,18 @@ def schedule(
             f"{unknown_costs} scheduled place(s)."
         )
 
+    if not budget_applies:
+        warnings.append(
+            f"Your budget is in {budget_currency} but prices here are in {currency}, "
+            f"so the budget was not applied (no currency conversion yet)."
+        )
+
+    if skipped_currency:
+        warnings.append(
+            f"{skipped_currency} place(s) were skipped because their prices "
+            f"are not in {currency}."
+        )
+
     if not placed:
         warnings.append(
             "No attractions fit the selected "
@@ -277,7 +367,7 @@ def schedule(
         )
 
     return {
-        "trip_id": str(uuid.uuid4()),
+        "trip_id": trip_id or str(uuid.uuid4()),
         "destination": normalized_destination,
         "start_date": dates[0],
         "end_date": dates[-1],
@@ -297,27 +387,49 @@ def plan_itinerary(
     destination: dict[str, Any],
     start_date: str,
     end_date: str,
-    city: str = "lisbon",
+    city: str | None = None,
+    trip_id: str | None = None,
 ) -> dict[str, Any]:
-    """Adapter used by the existing FastAPI endpoint."""
-    from api.contracts import load_categories, load_places
-
-    places = load_places(city)
+    """Adapter used by the FastAPI endpoints (same signature as the old stub).
+
+    Places come from the city named in `destination` (or from `city` when given), through
+    the Data team's catalog: a committed snapshot, the sample fixtures, or a live
+    OpenStreetMap fetch. Raises ingest.catalog.CityNotAvailable when there is no data for
+    that city (the API answers 422) and CityFetchFailed when OpenStreetMap is unreachable
+    (503). Pass `trip_id` when re-planning.
+    """
+    from api.contracts import load_categories
+    from ingest.catalog import load_city, travel_legs
+
+    # No silent default: a request without a city name is refused, never planned in Lisbon.
+    city_data = load_city(city or destination.get("name") or destination.get("city"))
     categories = load_categories()["categories"]
+    walking_limit = int(profile["max_walk_minutes"])
+
+    # The city's real name and its country, not however the traveler typed it.
+    dest = {
+        "name": ", ".join(filter(None, [city_data.name, city_data.country_name])),
+        "lat": float(destination.get("lat", city_data.destination["lat"])),
+        "lon": float(destination.get("lon", city_data.destination["lon"])),
+    }
+    country = destination.get("country") or city_data.destination.get("country")
+    if country:
+        dest["country"] = country
 
-    return schedule(
-        places=places,
+    itinerary = schedule(
+        places=city_data.places,
         profile=profile,
         dates=date_range(start_date, end_date),
+        # Travel times between the candidates, from the Data team's travel model.
+        travel_matrix=lambda candidates: travel_legs(candidates, walking_limit),
         category_map=categories,
-        destination={
-            "name": destination.get(
-                "name", city.title()
-            ),
-            "lat": destination.get("lat", 38.7223),
-            "lon": destination.get("lon", -9.1393),
-            **({
-                "country": destination["country"]
-            } if destination.get("country") else {}),
-        },
+        destination=dest,
+        trip_id=trip_id,
     )
+
+    if city_data.source == "fixture":
+        itinerary["warnings"].append(
+            f"Places for {city_data.name} come from the hand-made sample file, not live data."
+        )
+
+    return itinerary
diff --git a/optimizer/scoring.py b/optimizer/scoring.py
index a722fcf..bebe2db 100644
--- a/optimizer/scoring.py
+++ b/optimizer/scoring.py
@@ -36,13 +36,19 @@ def score(
     interests = profile.get("interests", {})
     matched = matched_interests(place, category_map)
 
-    interest_score = sum(
-        float(interests.get(name, 0.0))
-        for name in matched
+    # Use the traveler's strongest matching interest. Summing and dividing by the
+    # number of interests favoured places tagged with many categories, so a
+    # traveler whose top interest is food got palaces instead of restaurants.
+    interest_score = max(
+        (float(interests.get(name, 0.0)) for name in matched),
+        default=0.0,
     )
+    interest_score = max(0.0, min(1.0, interest_score))
 
-    interest_score /= max(1, len(interests))
-    interest_score = min(1.0, interest_score)
+    # A place that matches none of the traveler's interests is not a recommendation,
+    # however popular it is.
+    if interest_score <= 0:
+        return 0.0
 
     popularity = float(place.get("popularity", 0.5))
     rating = float(place.get("rating", 3.0)) / 5.0
diff --git a/optimizer/tests/__init__.py b/optimizer/tests/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/optimizer/test-scheduler.py b/optimizer/tests/test_scheduler.py
similarity index 50%
rename from optimizer/test-scheduler.py
rename to optimizer/tests/test_scheduler.py
index a8b5ef1..6861096 100644
--- a/optimizer/test-scheduler.py
+++ b/optimizer/tests/test_scheduler.py
@@ -180,3 +180,131 @@ def test_multi_day_schedule():
     assert len(result["days"]) == 2
     assert result["start_date"] == "2026-10-19"
     assert result["end_date"] == "2026-10-20"
+
+
+def _ids(result):
+    return [
+        item["place_id"]
+        for day in result["days"]
+        for item in day["items"]
+    ]
+
+
+def test_rejected_place_not_selected():
+    profile = deepcopy(PROFILE)
+    profile["feedback"] = {"accepted": [], "rejected": ["a"]}
+
+    result = run(
+        [make_place("a"), make_place("b")],
+        profile,
+    )
+
+    assert "a" not in _ids(result)
+    assert "b" in _ids(result)
+
+
+def test_trip_id_is_kept_when_replanning():
+    result = schedule(
+        places=[make_place("a")],
+        profile=PROFILE,
+        dates=["2026-10-19"],
+        category_map=CATEGORIES,
+        destination=DESTINATION,
+        trip_id="trip-123",
+    )
+
+    assert result["trip_id"] == "trip-123"
+
+
+def test_strongest_interest_wins():
+    # A traveler who loves food should get the restaurant before a palace that
+    # matches two weaker interests.
+    profile = deepcopy(PROFILE)
+    profile["interests"] = {"food": 0.9, "history": 0.4, "architecture": 0.4}
+    profile["pace"] = 0.0  # two stops a day
+
+    restaurant = make_place("restaurant")
+    restaurant["categories"] = ["restaurant"]
+    palace = make_place("palace")
+    palace["categories"] = ["palace"]
+
+    result = schedule(
+        places=[palace, restaurant],
+        profile=profile,
+        dates=["2026-10-19"],
+        category_map={
+            "restaurant": ["food"],
+            "palace": ["history", "architecture"],
+        },
+        destination=DESTINATION,
+    )
+
+    assert _ids(result)[0] == "restaurant"
+
+
+def test_place_matching_no_interest_is_skipped():
+    unrelated = make_place("bar")
+    unrelated["categories"] = ["bar"]
+
+    result = run([unrelated, make_place("museum")])
+
+    assert _ids(result) == ["museum"]
+
+
+def test_verified_hours_preferred_over_inferred():
+    inferred = deepcopy(HOURS)
+    inferred["confidence"] = "inferred"
+
+    result = run([
+        make_place("guess", hours=inferred),
+        make_place("verified"),
+    ])
+
+    assert _ids(result)[0] == "verified"
+    assert result["days"][0]["items"][0]["confidence"] == "known"
+
+
+def test_stray_currency_is_skipped_and_warned():
+    dollars = make_place("usd")
+    dollars["cost"]["currency"] = "USD"
+
+    result = run([dollars, make_place("eur"), make_place("eur-2")])
+
+    assert "usd" not in _ids(result)
+    assert any("not in EUR" in warning for warning in result["warnings"])
+
+
+def test_city_currency_is_used_when_budget_differs():
+    # A budget typed in USD for a city priced in EUR: plan anyway, total in EUR,
+    # and say the budget could not be applied instead of returning an empty trip.
+    profile = deepcopy(PROFILE)
+    profile["budget"] = {"total": 1, "currency": "USD"}
+
+    result = run([make_place("a", cost=50), make_place("b", cost=50)], profile)
+
+    assert len(_ids(result)) == 2
+    assert result["totals"]["currency"] == "EUR"
+    assert any("budget was not applied" in w for w in result["warnings"])
+
+
+def test_items_carry_the_place_name():
+    result = run([make_place("museum-1")])
+
+    assert result["days"][0]["items"][0]["name"] == "Place museum-1"
+
+
+def test_travel_matrix_can_be_built_for_the_candidates():
+    seen = []
+
+    def legs(candidates):
+        seen.extend(place["id"] for place in candidates)
+        return {
+            ("a", "b"): {"minutes": 7, "mode": "walk"},
+            ("b", "a"): {"minutes": 7, "mode": "walk"},
+        }
+
+    result = run([make_place("a"), make_place("b")], matrix=legs)
+
+    assert sorted(seen) == ["a", "b"]
+    second = result["days"][0]["items"][1]["travel_from_prev"]
+    assert second == {"minutes": 7, "mode": "walk"}
diff --git a/optimizer/travel.py b/optimizer/travel.py
index 8d036dc..f767dec 100644
--- a/optimizer/travel.py
+++ b/optimizer/travel.py
@@ -58,7 +58,8 @@ def travel_between(
         if minutes < 0:
             raise ValueError("Negative travel time")
 
-        return round(minutes), mode, False
+        # The Data team's legs are estimates too (no live routing), unless a leg says so.
+        return round(minutes), mode, bool(leg.get("estimated", True))
 
     straight_km = distance_km(first, second)
 
