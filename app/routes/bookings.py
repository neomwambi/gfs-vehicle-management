from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.models import Booking
from app.schemas.schemas import (
    BookingDecision,
    BookingOut,
    BookingRequestCreate,
    CheckInRequest,
    CheckOutRequest,
    MessageOut,
)
from app.services import booking as booking_service
from app.services.auth import AuthUser, get_current_user, require_manager

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


def _out(db: Session, booking: Booking) -> BookingOut:
    from datetime import datetime

    extras = booking_service._booking_out_extras(db, booking)
    can_approve = True
    reason = None
    if booking.BookingStatus == "Pending Approval" and booking.vehicle:
        status = booking.vehicle.CurrentStatus
        start = booking_service._as_naive_utc(booking.ReservationStart)
        now = datetime.utcnow()
        if booking.BookingType == "Immediate" and status != "Available":
            can_approve = False
            reason = (
                f"Vehicle is {status} - cannot approve an Immediate request until it is Available. "
                "Employee should use Advance Reservation for a future slot."
            )
        elif (
            booking.BookingType == "Advance Reservation"
            and start is not None
            and start <= now
            and status != "Available"
        ):
            can_approve = False
            reason = (
                f"Reservation start has passed and vehicle is {status}. "
                "Wait until Available, or reject and ask for a new request."
            )
    extras["CanApproveNow"] = can_approve
    extras["ApproveBlockedReason"] = reason
    base = BookingOut.model_validate(booking)
    return base.model_copy(update=extras)


@router.post("", response_model=BookingOut)
def create_booking(
    payload: BookingRequestCreate,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    booking = booking_service.request_booking(db, user, payload)
    return _out(db, booking)


@router.get("/mine", response_model=list[BookingOut])
def my_bookings(
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    rows = (
        db.query(Booking)
        .options(
            joinedload(Booking.vehicle),
            joinedload(Booking.driver),
            joinedload(Booking.approver),
        )
        .filter(Booking.DriverID == user.UserID)
        .order_by(Booking.RequestedAt.desc())
        .all()
    )
    return [_out(db, b) for b in rows]


@router.get("/pending", response_model=list[BookingOut])
def pending(
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_manager),
):
    return [_out(db, b) for b in booking_service.list_pending_sorted(db)]


@router.get("/awaiting-key-handover", response_model=list[BookingOut])
def awaiting_key_handover(
    db: Session = Depends(get_db),
    user: AuthUser = Depends(require_manager),
):
    rows = (
        db.query(Booking)
        .options(
            joinedload(Booking.vehicle),
            joinedload(Booking.driver),
            joinedload(Booking.approver),
        )
        .filter(
            Booking.BookingStatus == "Approved",
            Booking.KeyCollected.is_(False),
            Booking.ApprovedBy == user.UserID,
        )
        .order_by(Booking.ApprovalTimestamp.asc())
        .all()
    )
    return [_out(db, b) for b in rows]


@router.get("/awaiting-key-return", response_model=list[BookingOut])
def awaiting_key_return(
    db: Session = Depends(get_db),
    user: AuthUser = Depends(require_manager),
):
    rows = (
        db.query(Booking)
        .options(
            joinedload(Booking.vehicle),
            joinedload(Booking.driver),
            joinedload(Booking.approver),
        )
        .filter(
            Booking.BookingStatus == "Checked In",
            Booking.KeyReturned.is_(False),
            Booking.ApprovedBy == user.UserID,
        )
        .order_by(Booking.CheckInTimestamp.asc())
        .all()
    )
    return [_out(db, b) for b in rows]


@router.get("/active", response_model=list[BookingOut])
def active_trips(
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_manager),
):
    rows = (
        db.query(Booking)
        .options(
            joinedload(Booking.vehicle),
            joinedload(Booking.driver),
            joinedload(Booking.approver),
        )
        .filter(Booking.BookingStatus.in_(["Approved", "Checked Out", "Checked In", "Flagged"]))
        .order_by(Booking.RequestedAt.desc())
        .all()
    )
    return [_out(db, b) for b in rows]


@router.get("/{booking_id}", response_model=BookingOut)
def get_one(
    booking_id: int,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    booking = booking_service.get_booking(db, booking_id)
    if booking.DriverID != user.UserID and not user.is_manager_portal:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Not allowed to view this booking")
    return _out(db, booking)


@router.post("/{booking_id}/decide", response_model=BookingOut)
def decide(
    booking_id: int,
    payload: BookingDecision,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(require_manager),
):
    return _out(db, booking_service.decide_booking(db, user, booking_id, payload))


@router.post("/{booking_id}/key-collected", response_model=BookingOut)
def key_collected(
    booking_id: int,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(require_manager),
):
    return _out(db, booking_service.confirm_key_collected(db, user, booking_id))


@router.post("/{booking_id}/check-out", response_model=BookingOut)
def do_checkout(
    booking_id: int,
    payload: CheckOutRequest,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return _out(db, booking_service.check_out(db, user, booking_id, payload))


@router.post("/{booking_id}/check-in", response_model=BookingOut)
def do_checkin(
    booking_id: int,
    payload: CheckInRequest,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return _out(db, booking_service.check_in(db, user, booking_id, payload))


@router.post("/{booking_id}/key-returned", response_model=BookingOut)
def key_returned(
    booking_id: int,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(require_manager),
):
    return _out(db, booking_service.confirm_key_returned(db, user, booking_id))


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel(
    booking_id: int,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return _out(db, booking_service.cancel_booking(db, user, booking_id))
