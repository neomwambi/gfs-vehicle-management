# GFS Vehicle Management
## Stakeholder briefing

**Prepared by:** Neo Mwambi, Software Engineer  
**Audience:** Management and GFS operations team  
**Status:** Working local prototype — ready to demo  
**Date:** August 2026

This note is written for a mixed audience. The first half is the business story. The second half explains how the system is built, without assuming a software background, while still showing the engineering decisions behind it.

A live walkthrough takes about 10–15 minutes. Suggested demo accounts are at the end.

---

## 1. What this is

GFS Vehicle Management is a **pool-vehicle booking system** for Group Forensic Services.

It replaces informal “who has the car?” coordination with a single process:

1. An employee requests a vehicle and states **why** and **where**.
2. A manager **approves or rejects** in the admin portal.
3. The same manager confirms **key handover** in person.
4. The employee **checks out** with five camera photos, mileage, and location.
5. The employee **checks in** the same way, and can report damage.
6. The same manager confirms **key return**. The trip is closed.

Every meaningful step is written to an **audit log**. Missed check-out or overdue return does not silently cancel the trip — the booking is **flagged**, an incident is opened, and managers can still complete the process.

This is a **working prototype** you can click through on a laptop. It is designed so that bank-standard pieces (staff login, email, photo storage, production database) can be plugged in later without rewriting the booking rules.

---

## 2. Why it matters for GFS

| Operational need | What the prototype already does |
|------------------|----------------------------------|
| Know who has which car | Live vehicle status: Available, Reserved, or In Use |
| Control who may take a vehicle | Manager approval, with purpose and destination required |
| Physical key accountability | Only the approving manager can confirm handover and return |
| Condition of the vehicle | Five photos at check-out and check-in (front, back, left, right, odometer) |
| Mileage integrity | Check-out cannot be below current vehicle mileage; check-in cannot be below check-out |
| Damage visibility | Optional damage report opens an incident for manager review |
| Missed windows | Automatic flag if the employee does not check out or return in time |
| Oversight | Dashboard, incident queue, usage analytics, sent-email log, full audit trail |

Nothing is hard-deleted. Vehicles can only be switched off when they are not in use.

---

## 3. Who uses it

Two portals, one system.

| Role | Portal | Typical work |
|------|--------|----------------|
| Employee | `/app` | See cars, request, track my trips, check out, check in |
| Manager | `/admin` | Approvals, keys, incidents, analytics, fleet, emails, audit |
| Admin | `/admin` | Same screens as Manager in this prototype (separate profile for later) |

Demo sign-in (no password yet — Standard Bank SSO is the planned replacement):

| Sign in as | Username | Lands on |
|------------|----------|----------|
| Employee | `omphile` | Employee app |
| Manager | `nishen` | Admin portal |
| Admin | `neo` | Admin portal |

---

## 4. A trip from start to finish

This is the story to tell in the room. The diagram below is the same process the software enforces.

![Booking lifecycle](images/booking-flow.png)

**Happy path (blue):** Request → Pending → Approved → keys handed over → Checked Out → Checked In → Closed.

**If something goes wrong:**

- The employee can **cancel** only while the request is still pending.
- The manager can **reject**, but must give a reason.
- If the employee is late to check out or return, the trip is **Flagged** (orange). An incident is raised. The employee can still finish check-out or check-in — we do not strand a car in the system.

**Fairness:** pending requests are sorted by the driver’s borrowing record (Good, then Fair, then Poor), and then first-come-first-served. Approving one request automatically rejects overlapping pending requests for the same vehicle.

---

## 5. How it is built (framework)

Think of three layers:

1. **What people see** — web pages (employee app and admin portal).
2. **The rules** — a server that accepts or refuses each action (approve, check out, and so on).
3. **What is remembered** — a database, plus photo files on disk.

| Layer | Technology | In plain language |
|-------------------|-------------------|
| Screens | HTML, JavaScript, Bootstrap | Familiar web pages. No app store install. Works in Chrome or Edge. |
| Server | **FastAPI** (Python) | Industry-standard API framework. Serves both the pages and the data. |
| Database | **SQLite** today | A real relational database in a local file. Can move to Azure SQL later. |
| Photos | Files in `uploads/` | Camera captures stored per booking. Can move to Azure Blob later. |
| Sign-in | Temporary in-memory session | Fast for demos. Designed to be replaced with **Entra ID / SSO**. |
| Email | Written to a “Sent Emails” screen | Managers can already see what would have been emailed. Graph/SMTP later. |

**Why FastAPI?** It is a modern Python web framework used for production APIs. It gives us typed contracts (the server rejects incomplete requests before they become bad data), clear URL endpoints, and a clean split so login, email, and storage can be swapped without rewriting the booking process.

**What this is not:** it is not a PowerApp, not a spreadsheet, and not a React/mobile app. It is a purpose-built web system with a proper server, database, and audit trail.

---

## 6. Architecture

The picture below is the system as it runs today. Read it **top to bottom**.

![System architecture](images/architecture.png)

| Band on the diagram | What it means in the room |
|---------------------|---------------------------|
| **Browser** | Staff use either the employee portal or the admin portal after login. |
| **FastAPI** | One program receives every request. Different “routes” handle login, bookings, vehicles, admin, and a background timer. |
| **Services** | The business rules live here — especially `booking.py` (the trip state machine) and `deadlines.py` (missed-window scanner every 60 seconds). |
| **Persistence** | SQLite holds people, vehicles, bookings, incidents, and the audit log. Photos go to `uploads/`. |

Two engineering choices worth calling out:

- **The booking rules are separate from bank infrastructure.** Sign-in, email, photos, and the database URL sit in isolated modules. That is the Azure cutover path.
- **Employees cannot use admin APIs.** Even if someone typed an admin URL, the server returns “not allowed.” The screens also keep employees on the employee app.

A deeper technical tour (file map, improvement backlog) is in [ARCHITECTURE.md](../ARCHITECTURE.md).

---

## 7. Screens vs APIs — what actually happens on a click

The pages are not “dumb posters.” After a page loads, most **actions** talk to the server through **APIs**.

**API** = a named question or instruction the browser sends to the server, for example “create this booking” or “list my trips.” The server checks who you are, applies the rules, saves the result, and sends data back. The page then updates.

Two kinds of click:

| Kind | What it feels like | What the software does |
|------|--------------------|------------------------|
| **Navigation** | You move to another screen | The browser loads a new HTML page. No booking data is changed. |
| **API action** | You submit, approve, confirm, or save | JavaScript sends a request to `/api/...`. The database (and sometimes photos) change. |

Shared behaviour on every signed-in screen:

- **Opening the page** usually loads fresh data (an API **GET**).
- **Log out** always calls the logout API, then returns to the login screen.
- **Menu links** (Vehicles, My Trips, Approvals, Analytics, …) are navigation only.

### Login

| Control | API call? | What happens |
|---------|-----------|----------------|
| Page opens | Yes — `GET /api/auth/users` | Fills the demo user list |
| **Sign in (prototype)** | Yes — `POST /api/auth/login` | Issues a session; managers go to Admin, employees to the app |
| **Login with SSO** | No | Placeholder. Shows that Standard Bank SSO is the intended next step |

### Employee app

| Screen | Control | API call? |
|--------|---------|-----------|
| Vehicles | Page load | Yes — load fleet |
| Vehicles | **Request** / **Request a car** | No — opens the request form |
| Vehicles | **Not bookable** (grey) | No — disabled |
| Request | Page load | Yes — load vehicles for the dropdown |
| Request | Immediate vs Advance dropdown | No — only shows/hides date fields |
| Request | **Submit request** | Yes — `POST /api/bookings` |
| Request | Success popup OK | No |
| My Trips | Page load | Yes — load this user’s bookings |
| My Trips | **Cancel** | Yes — only while Pending |
| My Trips | **Check-Out** / **Check-In** links | No — open those screens |
| Check-Out / Check-In | Page load | Yes — load eligible bookings |
| Check-Out / Check-In | **Start camera** / **Capture** | No — uses the device camera in the browser |
| Check-Out / Check-In | **Submit** | Yes — photos, mileage, and location are saved |

Check-out and check-in are the heaviest API calls: five photos plus mileage and GPS text in one submit.

### Admin portal

| Screen | Control | API call? |
|--------|---------|-----------|
| Dashboard | Page load | Yes — counts plus active trips |
| Approvals | Page load | Yes — pending queue |
| Approvals | **Approve** / **Reject** | Yes — reject requires a typed reason |
| Keys | Page load | Yes — handover and return lists (only trips *you* approved) |
| Keys | **Confirm key handed over** | Yes |
| Keys | **Confirm key returned** | Yes — trip becomes Closed |
| Incidents | Page load | Yes |
| Incidents | Filter chips / search | No — filters the list already on screen |
| Incidents | **Save review** | Yes — Open / Under Review / Resolved |
| Analytics | Page load | Yes — km, destinations, risk, trends |
| Vehicles | Page load | Yes — full fleet including inactive |
| Vehicles | **Add vehicle** | Yes |
| Vehicles | Activate / deactivate | Yes — blocked if the car is in use |
| Sent Emails | Page load | Yes — simulated inbox |
| Audit Log | Page load | Yes — who changed what, and when |

---

## 8. What is production-ready vs still a prototype

Be explicit with leadership — this is a **controlled demo**, not a live bank system.

| Already working in the prototype | Planned for a bank environment |
|----------------------------------|--------------------------------|
| Full booking lifecycle, including keys and photos | Staff SSO (Entra ID) instead of a user dropdown |
| Role separation (employee vs manager/admin APIs) | HTTPS, hardened sessions, photos not publicly guessable |
| Audit log on every important change | Azure SQL instead of a local SQLite file |
| Automatic missed-window flags | Real email via Graph or SMTP |
| Service-due highlighting | Azure Blob for photos |
| Analytics on closed trips | Automated tests covering the full trip in CI |

The prototype already has the **swap points** named: database URL, auth module, photo storage, email module.

---

## 9. Suggested 12-minute demo

Use two browsers (or one normal window and one InPrivate window).

1. Sign in as **omphile**. Show the vehicle list.
2. **Request a car** — Immediate if a car is Available, otherwise Advance Reservation. Purpose and destination required.
3. Sign in as **nishen**. Open **Approvals**. Approve. Point out borrowing-record order.
4. Still as nishen, **Keys** → Confirm key handed over.
5. Back to omphile: **Check-Out** — camera, five angles, mileage, location. Submit.
6. **Check-In** — same photos; optionally tick damage.
7. Nishen: **Keys** → Confirm key returned. Status **Closed**.
8. Optional: **Audit Log** and **Sent Emails** to show traceability.

Reset demo data anytime with `python seed.py --reset`.

---

## 10. What I am asking of this group

This briefing is to show that a complete, auditable GFS pool-vehicle process already runs as software — not a slide deck.

Useful decisions from the team:

1. Confirm the **real-world process** matches this six-step handshake (especially “same manager for both key steps”).
2. Confirm **trip window** (currently 1 hour after keys / after check-out) vs what operations actually need.
3. Confirm whether **Manager** and **Admin** should stay the same, or Admin should get extra powers.
4. If we proceed, the next engineering slice is **SSO + locking down photos**, then real email, then Azure hosting.

I can run the demo live after this document, or leave the laptop on the employee and admin screens for questions.
