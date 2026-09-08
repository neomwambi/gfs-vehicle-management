# How to read this codebase — and how you would build it from scratch

This guide is for learning the GFS Vehicle Management System in order: what each layer does, which files to open first, how a booking request travels through the stack, and the sequence you would follow if you rebuilt the app yourself.

For diagrams and the booking state machine, also see [ARCHITECTURE.md](../ARCHITECTURE.md). For run commands, see [HOW_TO_RUN.txt](../HOW_TO_RUN.txt).

---

## 1. What you are looking at

One **FastAPI** process does everything:

| Piece | Job |
|-------|-----|
| JSON API | `/api/...` — login, vehicles, bookings, admin |
| HTML portals | `/login.html`, `/app/...`, `/admin/...` |
| Static assets | `/static/...` (CSS, JS, images) |
| Photo files | `/uploads/...` |
| Background task | Deadline scanner (missed check-out / overdue return) |

Data lives in **SQLite** (`data/gfs_vehicles.db`). Business rules live in **services**; routes stay thin. The browser is **vanilla JS + Bootstrap** (no React).

```
Browser (login / app / admin pages)
        │  fetch + X-Session-Token
        ▼
FastAPI (app/main.py)
   ├── routes/     HTTP endpoints (auth, validation, call services)
   ├── services/   Business rules (booking state machine, availability, email, audit)
   ├── models/     SQLAlchemy tables
   ├── schemas/    Pydantic request/response shapes
   └── static/     HTML + api.js + camera.js
        │
        ▼
SQLite + uploads/
```

---

## 2. Folder map (mental model)

```
GFS Vehicle Management System/
├── app/
│   ├── main.py              # Start here: creates the app, mounts routes & static files
│   ├── config.py            # Paths, trip window hours, photo angles, timezone
│   ├── database.py          # Engine, sessions, create_all + light migrations
│   ├── timeutil.py          # SA timezone helpers for calendar / midday rules
│   ├── models/models.py     # Tables: Users, Vehicles, Bookings, Incidents, …
│   ├── schemas/schemas.py   # What the API accepts/returns (validation)
│   ├── routes/              # HTTP layer only
│   │   ├── auth.py
│   │   ├── vehicles.py
│   │   ├── bookings.py      # Most of the employee + manager booking API
│   │   └── admin.py         # Approvals UI data, analytics, audit, vehicles admin
│   ├── services/            # Domain logic (the important “why”)
│   │   ├── auth.py          # In-memory session tokens (swap for Entra later)
│   │   ├── booking.py       # Request → approve → keys → check-out/in → close
│   │   ├── vehicles.py      # Available / Reserved / In Use + next-available dates
│   │   ├── deadlines.py     # Background flags for missed windows
│   │   ├── email.py         # Simulated emails → NotificationsLog
│   │   ├── storage.py       # Save check-out/in photos under uploads/
│   │   └── audit.py         # Append-only AuditLog rows
│   └── static/
│       ├── login.html
│       ├── js/api.js        # Shared fetch, session, header nav
│       ├── js/camera.js     # Photos + geolocation
│       ├── app/             # Employee portal pages
│       └── admin/           # Manager/Admin portal pages
├── seed.py                  # Demo users, fleet, sample bookings
├── tests/                   # Schema tests + optional live workflow
├── data/                    # SQLite file (gitignored)
└── uploads/                 # Photo files (gitignored)
```

---

## 3. Read the code in this order

Do not jump straight into admin analytics. Follow this path once; then explore sideways.

### Pass A — Skeleton (30–45 minutes)

| # | File | What to learn |
|---|------|----------------|
| 1 | `app/config.py` | Knobs: DB path, `TRIP_WINDOW_HOURS`, required photo angles, SA timezone |
| 2 | `app/database.py` | How sessions are opened (`get_db`) and tables created (`init_db`) |
| 3 | `app/models/models.py` | Domain nouns. Focus on **Booking** statuses and key/check-out fields |
| 4 | `app/main.py` | Lifespan (DB + deadline loop), routers, `/static` and HTML routes |
| 5 | `app/services/auth.py` | Login creates a token; every API call resolves `X-Session-Token` → user |

### Pass B — Happy-path booking (the heart of the app)

| # | File | What to learn |
|---|------|----------------|
| 6 | `app/schemas/schemas.py` | `BookingRequestCreate`, check-out/in payloads, photo rules |
| 7 | `app/services/booking.py` | State machine: `request_booking`, `decide`, keys, check-out, check-in, close |
| 8 | `app/routes/bookings.py` | Thin HTTP wrappers that call the service |
| 9 | `app/static/js/api.js` | How the browser stores the token and calls `/api/...` |
| 10 | `app/static/app/request.html` | Form → `POST /api/bookings` (also Photon/Leaflet destination) |
| 11 | `app/static/admin/approvals.html` | Manager decide flow |
| 12 | `app/static/app/checkout.html` + `checkin.html` | Photos via `camera.js` |

### Pass C — Supporting rules

| # | File | What to learn |
|---|------|----------------|
| 13 | `app/services/vehicles.py` | How fleet status and “next available” dates are computed (midday rule) |
| 14 | `app/services/deadlines.py` | Flagged bookings + Incidents when windows are missed |
| 15 | `app/services/email.py` + `audit.py` | Side effects on every major transition |
| 16 | `seed.py` | How demo data is shaped so the UI is interesting |
| 17 | `tests/test_validation.py` | What the API refuses before it hits the DB |

After Pass B you can explain the product to someone else. After Pass C you can change rules safely.

---

## 4. Trace one request end-to-end

Example: employee Omphile requests a vehicle.

1. **Browser** — `login.html` → `POST /api/auth/login` → token in `localStorage`.
2. **UI** — `request.html` builds JSON (`VehicleID`, times, purpose, destination, case number).
3. **HTTP** — `api.js` sends `POST /api/bookings` with header `X-Session-Token`.
4. **Route** — `routes/bookings.py` loads the user from the token, validates body with Pydantic.
5. **Service** — `booking.request_booking`:
   - Checks vehicle / overlaps / Immediate vs Advance rules
   - Inserts `Booking` with status `Pending Approval`
   - Writes audit + simulated email
6. **DB** — New row in `Bookings`.
7. **Manager** — `approvals.html` → `POST /api/bookings/{id}/decide`.
8. Later steps reuse the same pattern: **page → route → `booking.py` function → DB + email/audit**.

When something breaks, ask: *Did validation fail, did the service raise HTTPException, or did the UI never call the API?*

---

## 5. Booking status cheat sheet

```
Pending Approval
       │ decide approve / reject
       ▼
   Approved ──────────────► Rejected / Cancelled
       │ key collected
       ▼
  (deadline starts)
       │ check-out (5 photos + mileage + location)
       ▼
  Checked Out
       │ check-in (5 photos + mileage; optional damage)
       ▼
  Checked In
       │ key returned
       ▼
    Closed

Any missed check-out / overdue return window → Flagged (+ Incident),
but the driver can still complete check-out/check-in.
```

Vehicle `CurrentStatus` (`Available` | `Reserved` | `In Use`) is mostly **derived** from open bookings in `services/vehicles.py`, not typed in by hand on every screen.

---

## 6. How you would build this from scratch

If you rebuilt it (or mentored someone who did), use this order. Each step should leave you with something runnable.

### Step 0 — Problem and constraints

- Pool cars, manager approval, keys, photo proof, audit trail.
- Local prototype first; design modules so auth / DB / email / storage can swap to Azure later.

### Step 1 — Empty FastAPI app

1. Create venv, `requirements.txt` (fastapi, uvicorn, sqlalchemy, pydantic, …).
2. `app/main.py` with a `/health` route.
3. Run uvicorn; confirm docs at `/docs`.

### Step 2 — Config + database + models

1. `config.py` with `DATABASE_URL`, upload path, `TRIP_WINDOW_HOURS`.
2. `database.py` with engine + `get_db` + `Base`.
3. Model `User` and `Vehicle` only; `init_db()` on startup.
4. `seed.py` with a few users and cars.

### Step 3 — Mock auth

1. `POST /api/auth/login` → random token → in-memory map.
2. Dependency `get_current_user` reading `X-Session-Token`.
3. Login page that lists users and stores the token (`api.js`).

### Step 4 — Vertical slice: request a booking

1. Add `Booking` model + `BookingRequestCreate` schema.
2. Implement `request_booking` (minimal: no conflicts yet).
3. `POST /api/bookings` route.
4. `request.html` form.
5. Prove in `/docs` and in the UI that a Pending Approval row appears.

**This is the most important teaching step.** Everything else hangs off it.

### Step 5 — Approvals and conflicts

1. `decide` approve/reject + overlap rejection of competing pending requests.
2. Admin approvals page.
3. Email + audit helpers (even if email only writes to `NotificationsLog`).

### Step 6 — Keys, check-out, check-in, close

1. Key collected / returned (same approver rules as product requires).
2. Photo storage + five required angles.
3. Check-out / check-in mileage and location rules.
4. Set `CheckOutDeadline` / `CheckInDeadline` from `TRIP_WINDOW_HOURS`.

### Step 7 — Deadlines and incidents

1. Background `deadline_loop`.
2. Flag booking + create `Incident` when windows are missed.

### Step 8 — Availability UX

1. Derive vehicle status from bookings.
2. Expose next-available / blocked dates for the calendar (midday rule).
3. Polish employee vehicles list and request date pickers.

### Step 9 — Admin extras

Analytics, audit log viewer, incidents review, vehicle admin, destination map (Photon + Leaflet), favicon/branding.

### Step 10 — Tests and hardening

1. Schema/unit tests without a server.
2. Full workflow test (TestClient or live server).
3. Later: real auth, private uploads, Alembic migrations, Azure SQL.

---

## 7. Where to change what

| If you want to… | Touch… |
|-----------------|--------|
| Change approval / check-out rules | `app/services/booking.py` |
| Change trip window length | `TRIP_WINDOW_HOURS` in `app/config.py` |
| Change required photo angles | `REQUIRED_PHOTO_ANGLES` in `app/config.py` + UI |
| Change “when is the car free again?” | `app/services/vehicles.py` |
| Change missed-window behaviour | `app/services/deadlines.py` |
| Add an API field | `models` → `schemas` → service → route → HTML |
| Swap login to SSO | `app/services/auth.py` (+ login UI) |
| Swap email to real SMTP/Graph | `app/services/email.py` |
| Swap photos to blob storage | `app/services/storage.py` |
| Swap SQLite for Azure SQL | `DATABASE_URL` in `app/config.py` (+ migrations) |

---

## 8. Suggested exercises (learn by doing)

1. Add a new optional field on booking request (e.g. passenger count) through model → schema → service → request form → approvals view.
2. Shorten `TRIP_WINDOW_HOURS` to `0.05`, seed a trip, watch `deadlines.py` flag it.
3. Break a photo angle name in the UI and confirm schema validation rejects check-out.
4. Trace one Closed booking in the DB and match each timestamp to a function in `booking.py`.

---

## 9. Comments in the code

Core modules have short module and function comments focused on **business rules** (statuses, midday availability, tokens, deadlines). Start at the top of each file you open in the reading order above; those comments are the on-ramp.

When you add features, prefer the same style: explain *why* a rule exists, not what the next line of Python obviously does.
