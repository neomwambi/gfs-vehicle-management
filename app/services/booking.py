"""Booking workflow: request, approve, keys, check-out/in, cancel."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.config import TRIP_WINDOW_HOURS
from app.models.models import Booking, Incident, User, Vehicle
from app.schemas.schemas import (
    BookingDecision,
    BookingRequestCreate,
    CheckInRequest,
    CheckOutRequest,
)
from app.services import email as email_service
from app.services.audit import write_audit
from app.services.auth import AuthUser
from app.services.storage import save_photo
from app.services.vehicles import sync_vehicle_status


def _as_naive_utc(dt: datetime | None) -> datetime | None:
    """Normalize API/client datetimes to naive UTC for SQLite comparisons."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def borrowing_record(db: Session, driver_id: int) -> tuple[int, str]:
    """
    Higher score = better record.
    Deductions for damage incidents and missed-window flags.
    """
    score = 100
    incidents = (
        db.query(Incident)
        .join(Booking, Booking.BookingID == Incident.BookingID)
        .filter(Booking.DriverID == driver_id)
        .all()
    )
    for inc in incidents:
        if inc.FlagType == "Damage":
            score -= 25
        elif inc.FlagType in ("Missed Checkout Window", "Overdue Return"):
            score -= 20
        else:
            score -= 10
    score = max(0, score)
    if score >= 80:
        label = "Good"
    elif score >= 50:
        label = "Fair"
    else:
        label = "Poor"
    return score, label


def _booking_out_extras(db: Session, booking: Booking) -> dict:
    score, label = borrowing_record(db, booking.DriverID)
    return {
        "DriverName": booking.driver.DisplayName if booking.driver else None,
        "VehicleReg": booking.vehicle.RegistrationNumber if booking.vehicle else None,
        "VehicleMakeModel": booking.vehicle.MakeModel if booking.vehicle else None,
        "VehicleCurrentStatus": booking.vehicle.CurrentStatus if booking.vehicle else None,
        "ApproverName": booking.approver.DisplayName if booking.approver else None,
        "BorrowingRecordScore": score,
        "BorrowingRecordLabel": label,
    }


def _windows_overlap(start_a, end_a, start_b, end_b) -> bool:
    """True if two reservation windows overlap. Open-ended end is treated as far future."""
    far = datetime(9999, 1, 1)
    a0, a1 = start_a, end_a or far
    b0, b1 = start_b, end_b or far
    return a0 < b1 and b0 < a1


def _has_overlapping_hold(
    db: Session,
    *,
    vehicle_id: int,
    start: datetime,
    end: datetime | None,
    exclude_booking_id: int | None = None,
) -> Booking | None:
    """
    Calendar conflicts only (Pending / Approved bookings).
    Current possession (Checked Out / Checked In / Flagged) does not block a future Advance window -
    the car is expected to be returned before that reservation starts.
    """
    q = db.query(Booking).filter(
        Booking.VehicleID == vehicle_id,
        Booking.BookingStatus.in_(["Pending Approval", "Approved"]),
    )
    if exclude_booking_id:
        q = q.filter(Booking.BookingID != exclude_booking_id)
    for other in q.all():
        if _windows_overlap(start, end, other.ReservationStart, other.ReservationEnd):
            return other
    return None


def get_booking(db: Session, booking_id: int) -> Booking:
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.vehicle),
            joinedload(Booking.driver),
            joinedload(Booking.approver),
        )
        .filter(Booking.BookingID == booking_id)
        .first()
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


def request_booking(db: Session, user: AuthUser, payload: BookingRequestCreate) -> Booking:
    vehicle = db.get(Vehicle, payload.VehicleID)
    if not vehicle or not vehicle.IsActive:
        raise HTTPException(status_code=400, detail="Vehicle not found or inactive")

    now = datetime.utcnow()

    if payload.BookingType == "Immediate":
        # Immediate = need the car now - must be free
        if vehicle.CurrentStatus != "Available":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot request immediately: vehicle is {vehicle.CurrentStatus}. "
                    "Use Advance Reservation for a future date after it is returned."
                ),
            )
        open_hold = (
            db.query(Booking)
            .filter(
                Booking.VehicleID == vehicle.VehicleID,
                Booking.BookingStatus.in_(["Approved", "Checked Out", "Checked In", "Flagged"]),
            )
            .first()
        )
        if open_hold:
            raise HTTPException(
                status_code=400,
                detail="Vehicle already has an active approved or in-progress booking",
            )
        start = now
        end = None
    else:
        # Advance Reservation = future window only; may request while car is currently out
        start = _as_naive_utc(payload.ReservationStart)
        end = _as_naive_utc(payload.ReservationEnd)
        assert start is not None and end is not None
        if start <= now:
            raise HTTPException(
                status_code=400,
                detail="Advance Reservation start must be in the future",
            )
        overlap = _has_overlapping_hold(
            db, vehicle_id=vehicle.VehicleID, start=start, end=end
        )
        if overlap:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"That time window overlaps another booking "
                    f"(#{overlap.BookingID}, {overlap.BookingStatus}). Choose a different slot."
                ),
            )

    booking = Booking(
        VehicleID=vehicle.VehicleID,
        DriverID=user.UserID,
        BookingType=payload.BookingType,
        ReservationStart=start,
        ReservationEnd=end,
        PurposeReason=payload.PurposeReason.strip(),
        Destination=payload.Destination.strip(),
        BookingStatus="Pending Approval",
        RequestedAt=now,
    )
    db.add(booking)
    db.flush()

    write_audit(
        db,
        table_name="Bookings",
        record_id=booking.BookingID,
        action="CREATE",
        changed_by=user.UserID,
        new_value={
            "BookingStatus": booking.BookingStatus,
            "BookingType": booking.BookingType,
            "VehicleID": booking.VehicleID,
            "PurposeReason": booking.PurposeReason,
            "Destination": booking.Destination,
            "ReservationStart": start.isoformat(),
            "ReservationEnd": end.isoformat() if end else None,
        },
    )

    driver = db.get(User, user.UserID)
    assert driver
    email_service.notify_managers_new_request(db, booking, driver)
    db.commit()
    db.refresh(booking)
    return get_booking(db, booking.BookingID)


def cancel_booking(db: Session, user: AuthUser, booking_id: int) -> Booking:
    booking = get_booking(db, booking_id)
    if booking.DriverID != user.UserID and not user.is_manager_portal:
        raise HTTPException(status_code=403, detail="Cannot cancel another user's booking")
    if booking.BookingStatus != "Pending Approval":
        raise HTTPException(
            status_code=400,
            detail="Bookings can only be cancelled while Pending Approval",
        )
    old = booking.BookingStatus
    booking.BookingStatus = "Cancelled"
    write_audit(
        db,
        table_name="Bookings",
        record_id=booking.BookingID,
        action="CANCEL",
        changed_by=user.UserID,
        old_value={"BookingStatus": old},
        new_value={"BookingStatus": "Cancelled"},
    )
    db.commit()
    return get_booking(db, booking.BookingID)


def decide_booking(db: Session, user: AuthUser, booking_id: int, payload: BookingDecision) -> Booking:
    if not user.is_manager_portal:
        raise HTTPException(status_code=403, detail="Manager or Admin role required")

    booking = get_booking(db, booking_id)
    if booking.BookingStatus != "Pending Approval":
        raise HTTPException(status_code=400, detail="Only pending bookings can be approved or rejected")

    vehicle = booking.vehicle
    old_status = booking.BookingStatus
    now = datetime.utcnow()

    if payload.Decision == "Reject":
        booking.BookingStatus = "Rejected"
        booking.ApprovedBy = user.UserID
        booking.ApprovalTimestamp = now
        booking.RejectionReason = payload.RejectionReason.strip()
        write_audit(
            db,
            table_name="Bookings",
            record_id=booking.BookingID,
            action="REJECT",
            changed_by=user.UserID,
            old_value={"BookingStatus": old_status},
            new_value={"BookingStatus": "Rejected", "RejectionReason": booking.RejectionReason},
        )
        email_service.notify_employee_decision(db, booking, booking.driver, False, db.get(User, user.UserID))
        db.commit()
        return get_booking(db, booking.BookingID)

    # Approve
    if not vehicle.IsActive:
        raise HTTPException(status_code=400, detail="Cannot approve a booking for an inactive vehicle")

    if booking.BookingType == "Immediate":
        if vehicle.CurrentStatus != "Available":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot approve Immediate request: vehicle is {vehicle.CurrentStatus}. "
                    "Wait until it is returned, or ask the employee to submit an Advance Reservation."
                ),
            )
        competing = (
            db.query(Booking)
            .filter(
                Booking.VehicleID == vehicle.VehicleID,
                Booking.BookingStatus.in_(["Approved", "Checked Out", "Checked In", "Flagged"]),
                Booking.BookingID != booking.BookingID,
            )
            .first()
        )
        if competing:
            raise HTTPException(status_code=400, detail="Another booking already holds this vehicle")
    else:
        # Advance: may approve while car is currently out, if the reservation is still in the future
        if booking.ReservationStart <= now:
            if vehicle.CurrentStatus != "Available":
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Reservation start has passed and vehicle is {vehicle.CurrentStatus}. "
                        "Cannot approve until the vehicle is Available."
                    ),
                )
        overlap = _has_overlapping_hold(
            db,
            vehicle_id=vehicle.VehicleID,
            start=booking.ReservationStart,
            end=booking.ReservationEnd,
            exclude_booking_id=booking.BookingID,
        )
        # Pending others are handled by auto-reject; only block other Approved calendar holds
        if overlap and overlap.BookingStatus == "Approved":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot approve: overlaps approved booking #{overlap.BookingID}."
                ),
            )

    booking.BookingStatus = "Approved"
    booking.ApprovedBy = user.UserID
    booking.ApprovalTimestamp = now
    booking.RejectionReason = None
    # Only mark Reserved if nothing is currently using the car
    sync_vehicle_status(db, vehicle)
    if vehicle.CurrentStatus == "Available":
        vehicle.CurrentStatus = "Reserved"

    write_audit(
        db,
        table_name="Bookings",
        record_id=booking.BookingID,
        action="APPROVE",
        changed_by=user.UserID,
        old_value={"BookingStatus": old_status},
        new_value={
            "BookingStatus": "Approved",
            "ApprovedBy": user.UserID,
            "BookingType": booking.BookingType,
        },
    )

    # Auto-reject other pending requests that conflict (same vehicle Immediate, or overlapping Advance)
    others = (
        db.query(Booking)
        .options(joinedload(Booking.driver), joinedload(Booking.vehicle))
        .filter(
            Booking.VehicleID == vehicle.VehicleID,
            Booking.BookingStatus == "Pending Approval",
            Booking.BookingID != booking.BookingID,
        )
        .order_by(Booking.RequestedAt.asc())
        .all()
    )
    approver = db.get(User, user.UserID)
    for other in others:
        should_reject = False
        if booking.BookingType == "Immediate" or other.BookingType == "Immediate":
            should_reject = True
        elif _windows_overlap(
            booking.ReservationStart,
            booking.ReservationEnd,
            other.ReservationStart,
            other.ReservationEnd,
        ):
            should_reject = True
        if not should_reject:
            continue
        other.BookingStatus = "Rejected"
        other.ApprovedBy = user.UserID
        other.ApprovalTimestamp = now
        other.RejectionReason = (
            "Automatically rejected: another request for this vehicle was approved first (first-come basis)."
        )
        write_audit(
            db,
            table_name="Bookings",
            record_id=other.BookingID,
            action="REJECT_AUTO",
            changed_by=user.UserID,
            old_value={"BookingStatus": "Pending Approval"},
            new_value={"BookingStatus": "Rejected", "RejectionReason": other.RejectionReason},
        )
        email_service.notify_employee_decision(db, other, other.driver, False, approver)

    email_service.notify_employee_decision(db, booking, booking.driver, True, approver)
    db.commit()
    return get_booking(db, booking.BookingID)


def confirm_key_collected(db: Session, user: AuthUser, booking_id: int) -> Booking:
    if not user.is_manager_portal:
        raise HTTPException(status_code=403, detail="Manager or Admin role required")
    booking = get_booking(db, booking_id)
    if booking.BookingStatus != "Approved":
        raise HTTPException(status_code=400, detail="Key handover only applies to Approved bookings")
    if booking.KeyCollected:
        raise HTTPException(status_code=400, detail="Key already marked as collected")
    if booking.ApprovedBy != user.UserID:
        raise HTTPException(
            status_code=403,
            detail="Only the Manager/Admin who approved this booking can confirm key handover",
        )

    now = datetime.utcnow()
    booking.KeyCollected = True
    booking.KeyCollectedTimestamp = now
    booking.CheckOutDeadline = now + timedelta(hours=TRIP_WINDOW_HOURS)

    write_audit(
        db,
        table_name="Bookings",
        record_id=booking.BookingID,
        action="KEY_COLLECTED",
        changed_by=user.UserID,
        old_value={"KeyCollected": False},
        new_value={
            "KeyCollected": True,
            "KeyCollectedTimestamp": now.isoformat(),
            "CheckOutDeadline": booking.CheckOutDeadline.isoformat(),
        },
    )
    db.commit()
    return get_booking(db, booking.BookingID)


def check_out(db: Session, user: AuthUser, booking_id: int, payload: CheckOutRequest) -> Booking:
    booking = get_booking(db, booking_id)
    if booking.DriverID != user.UserID:
        raise HTTPException(status_code=403, detail="Only the assigned driver can check out")
    if booking.BookingStatus not in ("Approved", "Flagged"):
        raise HTTPException(
            status_code=400,
            detail="Check-out requires BookingStatus = Approved (or Flagged after a missed check-out window)",
        )
    if booking.CheckOutTimestamp is not None:
        raise HTTPException(status_code=400, detail="Check-out already completed for this booking")
    if not booking.KeyCollected:
        raise HTTPException(
            status_code=400,
            detail="Check-out blocked: key has not been confirmed collected by the approving manager",
        )

    vehicle = booking.vehicle
    if payload.Mileage < vehicle.CurrentMileage:
        raise HTTPException(
            status_code=400,
            detail=f"Check-out mileage ({payload.Mileage}) cannot be less than vehicle current mileage ({vehicle.CurrentMileage})",
        )

    paths = []
    for photo in payload.Photos:
        rel = save_photo(
            booking_id=booking.BookingID,
            phase="checkout",
            angle=photo.angle,
            data_url=photo.data_url,
        )
        paths.append({"angle": photo.angle, "path": rel})

    now = datetime.utcnow()
    old_status = booking.BookingStatus
    booking.CheckOutTimestamp = now
    booking.CheckOutMileage = payload.Mileage
    booking.CheckOutLocation = payload.LocationText.strip()
    booking.CheckOutLatitude = payload.Latitude
    booking.CheckOutLongitude = payload.Longitude
    booking.CheckOutPhotoPaths = json.dumps(paths)
    booking.CheckInDeadline = now + timedelta(hours=TRIP_WINDOW_HOURS)
    booking.BookingStatus = "Checked Out"
    booking.DamageNoted = payload.DamageNoted
    booking.DamageDescription = payload.DamageDescription.strip() if payload.DamageNoted else None
    vehicle.CurrentMileage = payload.Mileage
    vehicle.CurrentStatus = "In Use"

    write_audit(
        db,
        table_name="Bookings",
        record_id=booking.BookingID,
        action="CHECK_OUT",
        changed_by=user.UserID,
        old_value={"BookingStatus": old_status},
        new_value={
            "BookingStatus": "Checked Out",
            "CheckOutMileage": payload.Mileage,
            "CheckOutLocation": booking.CheckOutLocation,
            "CheckInDeadline": booking.CheckInDeadline.isoformat(),
            "DamageNoted": booking.DamageNoted,
            "DamageDescription": booking.DamageDescription,
            "Photos": paths,
        },
    )

    if booking.DamageNoted:
        incident = Incident(
            BookingID=booking.BookingID,
            FlagType="Damage at Check-Out",
            RaisedOn=now,
            ReviewStatus="Open",
            ResolutionNotes=None,
        )
        db.add(incident)
        db.flush()
        write_audit(
            db,
            table_name="Incidents",
            record_id=incident.IncidentID,
            action="CREATE",
            changed_by=user.UserID,
            new_value={"FlagType": "Damage at Check-Out", "BookingID": booking.BookingID},
        )
        email_service.notify_damage_reported(db, booking, booking.driver, phase="check-out")

    db.commit()
    return get_booking(db, booking.BookingID)


def check_in(db: Session, user: AuthUser, booking_id: int, payload: CheckInRequest) -> Booking:
    booking = get_booking(db, booking_id)
    if booking.DriverID != user.UserID:
        raise HTTPException(status_code=403, detail="Only the assigned driver can check in")
    if booking.BookingStatus not in ("Checked Out", "Flagged"):
        raise HTTPException(
            status_code=400,
            detail="Check-in requires BookingStatus = Checked Out (or Flagged after a missed window)",
        )
    if booking.CheckOutMileage is None:
        raise HTTPException(status_code=400, detail="Check-out mileage missing; cannot check in")
    if payload.Mileage < booking.CheckOutMileage:
        raise HTTPException(
            status_code=400,
            detail=f"Check-in mileage ({payload.Mileage}) must be >= check-out mileage ({booking.CheckOutMileage})",
        )

    paths = []
    for photo in payload.Photos:
        rel = save_photo(
            booking_id=booking.BookingID,
            phase="checkin",
            angle=photo.angle,
            data_url=photo.data_url,
        )
        paths.append({"angle": photo.angle, "path": rel})

    now = datetime.utcnow()
    old_status = booking.BookingStatus
    booking.CheckInTimestamp = now
    booking.CheckInMileage = payload.Mileage
    booking.CheckInLocation = payload.LocationText.strip()
    booking.CheckInLatitude = payload.Latitude
    booking.CheckInLongitude = payload.Longitude
    booking.CheckInPhotoPaths = json.dumps(paths)
    if payload.DamageNoted:
        booking.DamageNoted = True
        booking.DamageDescription = payload.DamageDescription.strip()
    booking.BookingStatus = "Checked In"
    booking.vehicle.CurrentMileage = payload.Mileage
    booking.vehicle.CurrentParkingLocation = booking.CheckInLocation
    sync_vehicle_status(db, booking.vehicle)

    write_audit(
        db,
        table_name="Bookings",
        record_id=booking.BookingID,
        action="CHECK_IN",
        changed_by=user.UserID,
        old_value={"BookingStatus": old_status},
        new_value={
            "BookingStatus": "Checked In",
            "CheckInMileage": payload.Mileage,
            "DamageNoted": booking.DamageNoted,
            "DamageDescription": booking.DamageDescription,
            "Photos": paths,
        },
    )

    if booking.DamageNoted:
        incident = Incident(
            BookingID=booking.BookingID,
            FlagType="Damage",
            RaisedOn=now,
            ReviewStatus="Open",
            ResolutionNotes=None,
        )
        db.add(incident)
        db.flush()
        write_audit(
            db,
            table_name="Incidents",
            record_id=incident.IncidentID,
            action="CREATE",
            changed_by=user.UserID,
            new_value={"FlagType": "Damage", "BookingID": booking.BookingID},
        )
        email_service.notify_damage_reported(db, booking, booking.driver)

    email_service.notify_managers_checkin_complete(db, booking, booking.driver)
    db.commit()
    return get_booking(db, booking.BookingID)


def confirm_key_returned(db: Session, user: AuthUser, booking_id: int) -> Booking:
    if not user.is_manager_portal:
        raise HTTPException(status_code=403, detail="Manager or Admin role required")
    booking = get_booking(db, booking_id)
    if booking.BookingStatus != "Checked In":
        raise HTTPException(status_code=400, detail="Key return only applies after Check-In")
    if booking.KeyReturned:
        raise HTTPException(status_code=400, detail="Key already marked as returned")
    if booking.ApprovedBy != user.UserID:
        raise HTTPException(
            status_code=403,
            detail="Only the Manager/Admin who approved this booking can confirm key return",
        )

    now = datetime.utcnow()
    old = booking.BookingStatus
    booking.KeyReturned = True
    booking.KeyReturnedTimestamp = now
    booking.BookingStatus = "Closed"
    sync_vehicle_status(db, booking.vehicle)

    write_audit(
        db,
        table_name="Bookings",
        record_id=booking.BookingID,
        action="KEY_RETURNED",
        changed_by=user.UserID,
        old_value={"BookingStatus": old, "KeyReturned": False},
        new_value={"BookingStatus": "Closed", "KeyReturned": True},
    )
    db.commit()
    return get_booking(db, booking.BookingID)


def list_pending_sorted(db: Session) -> list[Booking]:
    """FIFO within record bands: Good first, then Fair, then Poor; then RequestedAt."""
    rows = (
        db.query(Booking)
        .options(joinedload(Booking.vehicle), joinedload(Booking.driver), joinedload(Booking.approver))
        .filter(Booking.BookingStatus == "Pending Approval")
        .all()
    )
    band = {"Good": 0, "Fair": 1, "Poor": 2}

    def sort_key(b: Booking):
        score, label = borrowing_record(db, b.DriverID)
        return (band.get(label, 9), b.RequestedAt, -score)

    return sorted(rows, key=sort_key)
