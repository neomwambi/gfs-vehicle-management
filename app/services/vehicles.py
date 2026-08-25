"""Vehicle status and service-due helpers."""

from sqlalchemy.orm import Session, joinedload

from app.models.models import Booking, Vehicle

ACTIVE_BOOKING_STATUSES = {
    "Pending Approval",
    "Approved",
    "Checked Out",
    "Checked In",
    "Flagged",
}


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
