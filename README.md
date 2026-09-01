# GFS Vehicle Management System

Local prototype for Group Forensic Services pool-vehicle booking, approval, key handover, photo check-out/check-in, and audit trail.

- Presenting to management or operations? Use the [stakeholder briefing](docs/GFS-Vehicle-Management-Presentation.md).
- New to the codebase? Read the [architecture tour](ARCHITECTURE.md) for layers, the booking state machine, key files, and suggested first changes.

## Stack

- **Backend:** FastAPI + SQLAlchemy + SQLite
- **Frontend:** Bootstrap HTML/JS (`/app` employee portal, `/admin` manager portal)
- **Photos:** local `uploads/` (swap `app/services/storage.py` for Azure Blob later)
- **Auth:** mock sessions (`app/services/auth.py` → Entra ID later)
- **Email:** simulated log (`app/services/email.py` → Graph/SMTP later)

## Setup

```bash
cd "GFS Vehicle Management System"
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
python seed.py --reset
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/login.html

### Demo users

| Username | Name | Role |
|----------|------|------|
| Username | Name | Role |
|----------|------|------|
| nishen | Nishen Singh | Manager |
| neo | Neo Mwambi | Admin |
| omphile | Omphile Modiba | Employee |
| sboniso | Sboniso Shoba | Employee |
| faiz | Faiz Hoosen | Employee |
| karish | Karish Ramnarayan | Employee |
| riyaaz | Riyaaz Dadamia | Employee |
| leon | Leon Pottas | Employee |

Manager and Admin share the same `/admin` permissions (separate profiles).

### Reset demo data

```bash
python seed.py --reset
```

### Tests

```bash
pytest -q
```

## Workflow (short)

1. Employee requests a vehicle (Purpose + Destination required) → Pending Approval  
2. Manager approves/rejects in Admin → Approvals (email notifies both sides; approval is in-app)  
3. Approving manager confirms **key handover** → employee may check out  
4. Employee check-out: 5 camera photos + mileage + location (GPS + text)  
5. Employee check-in: 5 photos + mileage + optional **damage report**  
6. Same approving manager confirms **key return** → booking Closed  

Missed check-out / overdue return windows (`TRIP_WINDOW_HOURS` in `app/config.py`) are scanned every 60 seconds and raise incidents + notifications. Bookings become **Flagged** (not auto-cancelled).

## Azure migration touch-points

| Concern | Module |
|---------|--------|
| Database URL | `app/config.py` (`DATABASE_URL`) |
| Auth | `app/services/auth.py` |
| Photo storage | `app/services/storage.py` |
| Email | `app/services/email.py` |

## Notes

- Vehicles are soft-deactivated (`IsActive`); no hard deletes of vehicles or bookings.
- Employees cannot call `/api/admin/*` (403). UI also keeps them on `/app`.
- Camera capture uses `getUserMedia` (HTTPS or localhost).


-- Testing neo was here 
-- Testing on the v2 branch


-- More testing  -- Pro level 