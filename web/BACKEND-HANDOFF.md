# Backend handoff: what the new frontend features need

The frontend for **accounts, My trips, sharing, the day map and swap/add a stop** is done and
works today. Where the backend doesn't support a feature yet, the frontend runs in a stand-in
mode or hides the feature. This file lists what each backend owner needs to add to finish it.
Nothing in `web/` has to change when they do, apart from one setting for accounts.

| Feature | Works today with | Backend needed | Owner |
|---|---|---|---|
| Log in / sign up | Demo accounts kept in the browser | `/auth/*` endpoints | API |
| Save trips, My trips | Trips are saved on the server already; the list of which trips are yours is kept in the browser | `/me/trips` endpoints | API |
| Share a trip | **Works fully**: `#/trip/<id>` reads `GET /trips/{id}` | Nothing | – |
| Day map | Hidden: no stop has coordinates yet | `lat`/`lon` on itinerary items (contract change) | Optimizer + team |
| Swap / add a stop | Shows "not available yet" | `GET /trips/{id}/suggestions`; scheduler must keep accepted places | API + optimizer |

All errors can use FastAPI's usual `{"detail": ...}`. CORS already allows the `Authorization`
header (`allow_headers=["*"]` in `api/main.py`).

---

## 1. Accounts (`/auth`)

When these exist, set `VITE_AUTH_MODE=server` in `web/.env.local` and restart `npm run dev`.

| Method and path | Body | Success | Errors |
|---|---|---|---|
| `POST /auth/signup` | `{"name", "email", "password"}` | `201 {"user": {"id", "name", "email"}, "token"}` | `409` email taken, `422` invalid field |
| `POST /auth/login` | `{"email", "password"}` | `200 {"user", "token"}` | `401` wrong email or password |
| `GET /auth/me` | header `Authorization: Bearer <token>` | `200 {"id", "name", "email"}` | `401` missing, unknown or expired token |
| `POST /auth/logout` | header `Authorization: Bearer <token>` | `204` (deletes the session) | – |

- **Field errors:** `{"detail": {"field": "email" | "password" | "name", "message": "…"}}`
  makes the frontend show the message on that field. A plain string `detail` shows under the form.
- **Wrong email or password:** use one message for both, so the API doesn't reveal which
  emails have accounts: "That email and password don't match an account."
- The frontend sends emails trimmed and lower-cased, and passwords of at least 8 characters
  on sign-up. The backend should check both again.
- **Storage (SQLite, next to `trips`):**
  - `users(id TEXT PK, name, email UNIQUE, password_hash, created_at)`
  - `sessions(token_hash TEXT PK, user_id, expires_at)`
- **Passwords:** `hashlib.scrypt` from the standard library, with a random 16-byte salt per
  user. Store `salt + hash` and compare with `hmac.compare_digest`. Never store or log the
  password itself.
- **Tokens:** `secrets.token_urlsafe(32)`. Store only its SHA-256, and expire it after 30 days.

## 2. My trips (`/me/trips`)

All of these need `Authorization: Bearer <token>`. A missing or bad token gets `401`.

| Method and path | Body | Success |
|---|---|---|
| `GET /me/trips` | – | `200 [SavedTrip, …]` |
| `PUT /me/trips/{trip_id}` | `{"request": PlanRequest or null}` | `200 SavedTrip`, or `404` if no such trip. Saving twice updates the entry. |
| `DELETE /me/trips/{trip_id}` | – | `204` |

```json
SavedTrip = {
  "trip_id": "…", "destination": "Rome, Italy",
  "start_date": "2026-12-10", "end_date": "2026-12-12", "days": 3,
  "saved_at": "2026-11-18T14:00:00Z",
  "request": { "…the PlanRequest the trip was planned from, or null" }
}
```

- Work out `destination`, `start_date`, `end_date` and `days` from the stored itinerary.
- **Storage:** `saved_trips(user_id, trip_id, request, saved_at, PRIMARY KEY (user_id, trip_id))`.
- Opening a saved trip uses the existing `GET /trips/{id}`, so it always shows the latest plan.

## 3. Sharing

Nothing is needed: a share link is `…/#/trip/<trip_id>`, and the page reads `GET /trips/{id}`.
**Worth deciding as a team:** today anyone who has a trip id can also re-plan it, through
`POST /trips/{id}/feedback`. Once accounts exist, consider allowing feedback only from the
trip's owner, and keeping `GET /trips/{id}` open for share links.

## 4. Day map: coordinates on itinerary items (`/contracts` change, needs team agreement)

Add optional `lat` and `lon` to the item in `contracts/itinerary.schema.json`, and have the
optimizer copy them from the place onto each scheduled item. A ready draft is in
`backend-day-map-coordinates.patch`; all 404 Python tests pass with it. The map then appears
by itself.

Map tiles come from OpenStreetMap (`tile.openstreetmap.org`, credited on the map). That's
fine for a class project. For heavy use, set `VITE_MAP_TILES` to another tile provider's URL.

## 5. Swap or add a stop

**New endpoint:** `GET /trips/{trip_id}/suggestions?replace=<place_id>&date=<YYYY-MM-DD>`
(both optional) returns:

```json
{ "suggestions": [
  { "place_id": "osm:node/123", "name": "Trevi Fountain",
    "reason": "Matches your interest in architecture.", "cost": 0, "cost_confidence": "known" }
] }
```

- Up to 5 places, best first, using the same scoring as planning.
- Leave out places already in the trip or rejected.
- Prefer places open on `date`, and near the stop being replaced.
- `reason` uses the optimizer's wording, so the right map-legend icon shows.
- If the trip id doesn't exist, return `404` with the usual "No trip with id …" message.
  Until the endpoint exists, FastAPI's plain 404 makes the UI say "not available yet".

**Applying the choice uses the existing feedback endpoint:**
`POST /trips/{id}/feedback` with `{"accepted": [new_place], "rejected": [swapped_out_place]}`
(for "add", `rejected` is empty). Today the scheduler only records accepted places. It needs
to **treat accepted places as must-visit** and schedule them when they fit. The frontend
checks the new plan and tells the traveler when the chosen place couldn't be fitted.
