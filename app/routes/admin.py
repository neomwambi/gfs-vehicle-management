from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.models import AuditLog, Booking, Incident, NotificationsLog, User
from app.schemas.schemas import (
    AuditLogOut,
    DashboardOut,
    IncidentOut,
    IncidentReview,
    NotificationOut,
)
from app.services.audit import write_audit
from app.services.auth import AuthUser, require_manager
from app.services.vehicles import is_service_due_soon
from app.models.models import Vehicle

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    db: Session = Depends(get_db),
    user: AuthUser = Depends(require_manager),
):
    open_incidents = db.query(Incident).filter(Incident.ReviewStatus != "Resolved").count()
    vehicles = db.query(Vehicle).filter(Vehicle.IsActive.is_(True)).all()
    nearing = sum(1 for v in vehicles if is_service_due_soon(v))
    active = (
        db.query(Booking)
        .filter(Booking.BookingStatus.in_(["Approved", "Checked Out", "Checked In", "Flagged"]))
        .count()
    )
    missed = (
        db.query(Incident)
        .filter(
            Incident.FlagType.in_(["Missed Checkout Window", "Overdue Return"]),
            Incident.ReviewStatus != "Resolved",
        )
        .count()
    )
    pending = db.query(Booking).filter(Booking.BookingStatus == "Pending Approval").count()
    handover = (
        db.query(Booking)
        .filter(
            Booking.BookingStatus == "Approved",
            Booking.KeyCollected.is_(False),
            Booking.ApprovedBy == user.UserID,
        )
        .count()
    )
    key_return = (
        db.query(Booking)
        .filter(
            Booking.BookingStatus == "Checked In",
            Booking.KeyReturned.is_(False),
            Booking.ApprovedBy == user.UserID,
        )
        .count()
    )
    return DashboardOut(
        OpenIncidents=open_incidents,
        VehiclesNearingService=nearing,
        ActiveTrips=active,
        MissedWindows=missed,
        PendingApprovals=pending,
        AwaitingKeyHandover=handover,
        AwaitingKeyReturn=key_return,
    )


@router.get("/incidents", response_model=list[IncidentOut])
def list_incidents(
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_manager),
):
    rows = (
        db.query(Incident)
        .options(joinedload(Incident.booking).joinedload(Booking.driver), joinedload(Incident.booking).joinedload(Booking.vehicle))
        .order_by(Incident.RaisedOn.desc())
        .all()
    )
    out = []
    for i in rows:
        out.append(
            IncidentOut(
                IncidentID=i.IncidentID,
                BookingID=i.BookingID,
                FlagType=i.FlagType,
                RaisedOn=i.RaisedOn,
                ReviewedBy=i.ReviewedBy,
                ReviewStatus=i.ReviewStatus,
                ResolutionNotes=i.ResolutionNotes,
                DriverName=i.booking.driver.DisplayName if i.booking and i.booking.driver else None,
                VehicleReg=i.booking.vehicle.RegistrationNumber if i.booking and i.booking.vehicle else None,
            )
        )
    return out


@router.post("/incidents/{incident_id}/review", response_model=IncidentOut)
def review_incident(
    incident_id: int,
    payload: IncidentReview,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(require_manager),
):
    incident = db.get(Incident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    old = {"ReviewStatus": incident.ReviewStatus, "ResolutionNotes": incident.ResolutionNotes}
    incident.ReviewStatus = payload.ReviewStatus
    incident.ResolutionNotes = payload.ResolutionNotes
    incident.ReviewedBy = user.UserID
    write_audit(
        db,
        table_name="Incidents",
        record_id=incident.IncidentID,
        action="REVIEW",
        changed_by=user.UserID,
        old_value=old,
        new_value={"ReviewStatus": incident.ReviewStatus, "ResolutionNotes": incident.ResolutionNotes},
    )
    db.commit()
    booking = (
        db.query(Booking)
        .options(joinedload(Booking.driver), joinedload(Booking.vehicle))
        .filter(Booking.BookingID == incident.BookingID)
        .first()
    )
    return IncidentOut(
        IncidentID=incident.IncidentID,
        BookingID=incident.BookingID,
        FlagType=incident.FlagType,
        RaisedOn=incident.RaisedOn,
        ReviewedBy=incident.ReviewedBy,
        ReviewStatus=incident.ReviewStatus,
        ResolutionNotes=incident.ResolutionNotes,
        DriverName=booking.driver.DisplayName if booking and booking.driver else None,
        VehicleReg=booking.vehicle.RegistrationNumber if booking and booking.vehicle else None,
    )


@router.get("/notifications", response_model=list[NotificationOut])
def notifications(
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_manager),
):
    rows = db.query(NotificationsLog).order_by(NotificationsLog.SentAt.desc()).limit(200).all()
    return [NotificationOut.model_validate(r) for r in rows]


@router.get("/audit", response_model=list[AuditLogOut])
def audit_log(
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_manager),
):
    rows = db.query(AuditLog).order_by(AuditLog.ChangedAt.desc()).limit(300).all()
    users = {u.UserID: u.DisplayName for u in db.query(User).all()}
    return [
        AuditLogOut(
            LogID=r.LogID,
            TableName=r.TableName,
            RecordID=r.RecordID,
            Action=r.Action,
            ChangedBy=r.ChangedBy,
            ChangedByName=users.get(r.ChangedBy) if r.ChangedBy else "System",
            ChangedAt=r.ChangedAt,
            OldValue=r.OldValue,
            NewValue=r.NewValue,
        )
        for r in rows
    ]


@router.get("/analytics")
def analytics(
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_manager),
):
    bookings = (
        db.query(Booking)
        .options(joinedload(Booking.driver), joinedload(Booking.vehicle))
        .all()
    )
    closed = [
        b
        for b in bookings
        if b.BookingStatus == "Closed"
        and b.CheckOutMileage is not None
        and b.CheckInMileage is not None
    ]
    incidents = (
        db.query(Incident)
        .options(
            joinedload(Incident.booking).joinedload(Booking.driver),
            joinedload(Incident.booking).joinedload(Booking.vehicle),
        )
        .order_by(Incident.RaisedOn.desc())
        .all()
    )

    km_per_driver: dict[str, int] = {}
    trips_per_driver: dict[str, int] = {}
    km_per_vehicle: dict[str, int] = {}
    trips_per_vehicle: dict[str, int] = {}
    trips_by_month: dict[str, dict[str, int]] = {}
    destinations: dict[str, int] = {}
    booking_types: dict[str, int] = {}
    status_breakdown: dict[str, int] = {}
    duration_hours: list[float] = []
    total_km = 0

    for b in bookings:
        status_breakdown[b.BookingStatus] = status_breakdown.get(b.BookingStatus, 0) + 1
        booking_types[b.BookingType] = booking_types.get(b.BookingType, 0) + 1

    for b in closed:
        name = b.driver.DisplayName if b.driver else str(b.DriverID)
        reg = b.vehicle.RegistrationNumber if b.vehicle else str(b.VehicleID)
        km = max(0, (b.CheckInMileage or 0) - (b.CheckOutMileage or 0))
        total_km += km
        km_per_driver[name] = km_per_driver.get(name, 0) + km
        trips_per_driver[name] = trips_per_driver.get(name, 0) + 1
        km_per_vehicle[reg] = km_per_vehicle.get(reg, 0) + km
        trips_per_vehicle[reg] = trips_per_vehicle.get(reg, 0) + 1
        dest = (b.Destination or "Unknown").strip()
        destinations[dest] = destinations.get(dest, 0) + 1

        month_key = (b.CheckOutTimestamp or b.RequestedAt).strftime("%Y-%m")
        bucket = trips_by_month.setdefault(month_key, {"Trips": 0, "Km": 0})
        bucket["Trips"] += 1
        bucket["Km"] += km

        if b.CheckOutTimestamp and b.CheckInTimestamp:
            hours = (b.CheckInTimestamp - b.CheckOutTimestamp).total_seconds() / 3600.0
            if hours > 0:
                duration_hours.append(hours)

    incidents_by_type: dict[str, int] = {}
    incidents_by_status: dict[str, int] = {}
    incidents_by_month: dict[str, int] = {}
    incidents_per_driver: dict[str, int] = {}
    incidents_per_vehicle: dict[str, int] = {}

    for i in incidents:
        incidents_by_type[i.FlagType] = incidents_by_type.get(i.FlagType, 0) + 1
        incidents_by_status[i.ReviewStatus] = incidents_by_status.get(i.ReviewStatus, 0) + 1
        mk = i.RaisedOn.strftime("%Y-%m")
        incidents_by_month[mk] = incidents_by_month.get(mk, 0) + 1
        if i.booking and i.booking.driver:
            dname = i.booking.driver.DisplayName
            incidents_per_driver[dname] = incidents_per_driver.get(dname, 0) + 1
        if i.booking and i.booking.vehicle:
            vreg = i.booking.vehicle.RegistrationNumber
            incidents_per_vehicle[vreg] = incidents_per_vehicle.get(vreg, 0) + 1

    driver_names = sorted(set(km_per_driver) | set(incidents_per_driver) | set(trips_per_driver))
    driver_risk = []
    for name in driver_names:
        trips = trips_per_driver.get(name, 0)
        inc_count = incidents_per_driver.get(name, 0)
        driver_risk.append(
            {
                "Driver": name,
                "Trips": trips,
                "Km": km_per_driver.get(name, 0),
                "Incidents": inc_count,
                "IncidentsPerTrip": round(inc_count / trips, 2) if trips else None,
            }
        )
    driver_risk.sort(key=lambda r: (-(r["Incidents"]), -r["Km"]))

    vehicle_regs = sorted(set(trips_per_vehicle) | set(incidents_per_vehicle) | set(km_per_vehicle))
    vehicle_utilization = []
    for reg in vehicle_regs:
        trips = trips_per_vehicle.get(reg, 0)
        vehicle_utilization.append(
            {
                "Registration": reg,
                "Trips": trips,
                "Km": km_per_vehicle.get(reg, 0),
                "Incidents": incidents_per_vehicle.get(reg, 0),
            }
        )
    vehicle_utilization.sort(key=lambda r: (-r["Trips"], -r["Km"]))

    month_keys = sorted(set(trips_by_month) | set(incidents_by_month))
    trips_trend = [
        {
            "Month": m,
            "Trips": trips_by_month.get(m, {}).get("Trips", 0),
            "Km": trips_by_month.get(m, {}).get("Km", 0),
            "Incidents": incidents_by_month.get(m, 0),
        }
        for m in month_keys
    ]

    top_destinations = sorted(
        [{"Destination": k, "Trips": v} for k, v in destinations.items()],
        key=lambda x: -x["Trips"],
    )[:8]

    open_inc = sum(1 for i in incidents if i.ReviewStatus != "Resolved")
    resolved_inc = sum(1 for i in incidents if i.ReviewStatus == "Resolved")
    damage_inc = sum(1 for i in incidents if "Damage" in i.FlagType)
    missed_inc = sum(
        1 for i in incidents if i.FlagType in ("Missed Checkout Window", "Overdue Return")
    )
    rejected = status_breakdown.get("Rejected", 0)
    reject_base = rejected + len(closed) + status_breakdown.get("Checked Out", 0) + status_breakdown.get(
        "Checked In", 0
    ) + status_breakdown.get("Approved", 0) + status_breakdown.get("Flagged", 0)

    avg_km = round(total_km / len(closed), 1) if closed else 0
    avg_hours = round(sum(duration_hours) / len(duration_hours), 1) if duration_hours else 0
    incident_rate = round((len(incidents) / len(closed)) * 100, 1) if closed else 0

    incident_history = [
        {
            "IncidentID": i.IncidentID,
            "FlagType": i.FlagType,
            "RaisedOn": i.RaisedOn.isoformat(),
            "ReviewStatus": i.ReviewStatus,
            "BookingID": i.BookingID,
            "DriverName": i.booking.driver.DisplayName if i.booking and i.booking.driver else None,
            "VehicleReg": i.booking.vehicle.RegistrationNumber
            if i.booking and i.booking.vehicle
            else None,
            "ResolutionNotes": i.ResolutionNotes,
        }
        for i in incidents
    ]

    return {
        "Summary": {
            "ClosedTripCount": len(closed),
            "TotalKmDriven": total_km,
            "AvgKmPerTrip": avg_km,
            "AvgTripDurationHours": avg_hours,
            "TotalBookings": len(bookings),
            "OpenIncidents": open_inc,
            "ResolvedIncidents": resolved_inc,
            "DamageIncidents": damage_inc,
            "MissedWindowIncidents": missed_inc,
            "IncidentRatePct": incident_rate,
            "RejectionRatePct": round((rejected / reject_base) * 100, 1) if reject_base else 0,
            "ImmediatePct": round(
                (booking_types.get("Immediate", 0) / len(bookings)) * 100, 1
            )
            if bookings
            else 0,
            "AdvancePct": round(
                (booking_types.get("Advance Reservation", 0) / len(bookings)) * 100, 1
            )
            if bookings
            else 0,
        },
        "KmPerDriver": dict(sorted(km_per_driver.items(), key=lambda x: -x[1])),
        "TripsPerDriver": dict(sorted(trips_per_driver.items(), key=lambda x: -x[1])),
        "KmPerVehicle": dict(sorted(km_per_vehicle.items(), key=lambda x: -x[1])),
        "TripsPerVehicle": dict(sorted(trips_per_vehicle.items(), key=lambda x: -x[1])),
        "BookingStatusBreakdown": status_breakdown,
        "BookingTypeBreakdown": booking_types,
        "IncidentsByType": incidents_by_type,
        "IncidentsByStatus": incidents_by_status,
        "TripsTrend": trips_trend,
        "TopDestinations": top_destinations,
        "DriverRisk": driver_risk,
        "VehicleUtilization": vehicle_utilization,
        "IncidentHistory": incident_history,
        "ClosedTripCount": len(closed),
    }
