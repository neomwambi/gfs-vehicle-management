"""Vehicle status and service-due helpers."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from sqlalchemy.orm import Session, joinedload

from app.config import TRIP_WINDOW_HOURS
from app.models.models import Booking, Vehicle

ACTIVE_BOOKING_STATUSES = {
    "Pending Approval",
    "Approved",
    "Checked Out",
    "Checked In",
    "Flagged",
}

SCHEDULE_STATUSES = {
    "Pending Approval",
    "Approved",
    "Checked Out",
    "Checked In",
    "Flagged",
}

# Return before midday → same-day afternoon bookings allowed from this hour.
AFTERNOON_OPEN_HOUR = 12


def km_until_service(vehicle: Vehicle) -> int:
    due_at = vehicle.LastServiceMileage + vehicle.ServiceIntervalKm
    return due_at - vehicle.CurrentMileage


def is_service_due_soon(vehicle: Vehicle) -> bool:
    return km_until_service(vehicle) <= vehicle.ServiceAlertThresholdKm


def current_holder(db: Session, vehicle_id: int) -> Booking | None:
    return (
        db.query(Booking)
        .options(joinedload(Booking.driver))
        .filter(
            Booking.VehicleID == vehicle_id,
            Booking.BookingStatus.in_(["Approved", "Checked Out", "Checked In", "Flagged"]),
        )
        .order_by(Booking.BookingID.desc())
        .first()
    )


def sync_vehicle_status(db: Session, vehicle: Vehicle) -> None:
    """Derive CurrentStatus from open bookings. Does not change IsActive."""
    # In use: actively checked out, or flagged overdue return (checked out, not yet checked in)
    open_bookings = (
        db.query(Booking)
        .filter(
            Booking.VehicleID == vehicle.VehicleID,
            Booking.BookingStatus.in_(["Approved", "Checked Out", "Checked In", "Flagged"]),
        )
        .all()
    )
    for b in open_bookings:
        if b.CheckOutTimestamp and not b.CheckInTimestamp:
            vehicle.CurrentStatus = "In Use"
            return

    if open_bookings:
        # Keys out / approved / awaiting key return after check-in
        vehicle.CurrentStatus = "Reserved"
        return

    vehicle.CurrentStatus = "Available"


def employee_visible_vehicles(db: Session) -> list[Vehicle]:
    return (
        db.query(Vehicle)
        .filter(Vehicle.IsActive.is_(True))
        .order_by(Vehicle.RegistrationNumber)
        .all()
    )


def _booking_window(booking: Booking) -> tuple[datetime, datetime | None]:
    """Best-effort busy window for availability / calendar blocking."""
    if booking.CheckOutTimestamp and not booking.CheckInTimestamp:
        start = booking.CheckOutTimestamp
        end = booking.CheckInDeadline or booking.ReservationEnd
        if end is None:
            end = start + timedelta(hours=TRIP_WINDOW_HOURS)
        return start, end

    if booking.CheckInTimestamp and booking.BookingStatus == "Checked In" and not booking.KeyReturned:
        return booking.CheckInTimestamp, booking.CheckInTimestamp + timedelta(minutes=30)

    start = booking.ReservationStart
    end = booking.ReservationEnd
    if end is None and booking.BookingType == "Immediate":
        anchor = booking.ApprovalTimestamp or booking.KeyCollectedTimestamp or booking.ReservationStart
        end = anchor + timedelta(hours=TRIP_WINDOW_HOURS)
    return start, end


def free_from_after_return(end: datetime) -> datetime:
    """
    Midday rule:
    - Returned before 12:00 → bookable from 12:00 the same day (afternoon).
    - Returned at/after 12:00 → next calendar day.
    """
    if end.time() < time(AFTERNOON_OPEN_HOUR, 0):
        return datetime.combine(end.date(), time(AFTERNOON_OPEN_HOUR, 0))
    return datetime.combine(end.date() + timedelta(days=1), time(0, 0))


def _mark_dates_for_hold(
    start: datetime,
    end: datetime,
    *,
    unavailable: set[str],
    afternoon_only: set[str],
) -> datetime:
    """Apply a hold to calendar date sets; return when the car is free after this hold."""
    free_from = free_from_after_return(end)
    d = start.date()
    while d < free_from.date():
        unavailable.add(d.isoformat())
        afternoon_only.discard(d.isoformat())
        d += timedelta(days=1)

    if free_from.time() >= time(AFTERNOON_OPEN_HOUR, 0) and free_from.hour == AFTERNOON_OPEN_HOUR:
        key = free_from.date().isoformat()
        if key not in unavailable:
            afternoon_only.add(key)

    return free_from


def vehicle_availability(db: Session, vehicle: Vehicle) -> dict:
    """
    NextAvailableFrom uses the midday rule for the current hold.
    UnavailableDates are fully greyed; AfternoonOnlyDates stay selectable from 12:00.
    No driver / booking detail is exposed.
    """
    now = datetime.utcnow()
    rows = (
        db.query(Booking)
        .filter(
            Booking.VehicleID == vehicle.VehicleID,
            Booking.BookingStatus.in_(SCHEDULE_STATUSES),
        )
        .order_by(Booking.ReservationStart.asc())
        .all()
    )

    unavailable: set[str] = set()
    afternoon_only: set[str] = set()
    next_available: datetime | None = None

    for b in rows:
        start, end = _booking_window(b)
        if end is None:
            end = start + timedelta(hours=TRIP_WINDOW_HOURS)

        is_out = bool(b.CheckOutTimestamp and not b.CheckInTimestamp)
        is_reserved = b.BookingStatus == "Approved" and not b.CheckOutTimestamp
        is_awaiting_keys = b.BookingStatus == "Checked In" and not b.KeyReturned
        is_current = is_out or is_reserved or is_awaiting_keys

        if not is_current and end < now:
            continue

        if is_current and end < now:
            end = now

        free_from = _mark_dates_for_hold(
            start, end, unavailable=unavailable, afternoon_only=afternoon_only
        )

        if is_current:
            candidate = free_from if free_from > now else now
            if next_available is None or candidate < next_available:
                next_available = candidate

    if vehicle.CurrentStatus == "Available":
        next_available = now
        # Still keep future reservation dates greyed via loop above

    return {
        "NextAvailableFrom": next_available,
        "UnavailableDates": sorted(unavailable),
        "AfternoonOnlyDates": sorted(afternoon_only - unavailable),
    }
