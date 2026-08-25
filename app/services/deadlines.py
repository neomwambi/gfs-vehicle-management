"""Deadline scanner for missed check-out / overdue return windows.

Runs as a FastAPI background task every DEADLINE_CHECK_INTERVAL_SECONDS.
Best for the prototype: works even if nobody has a browser open.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from app.config import DEADLINE_CHECK_INTERVAL_SECONDS
from app.database import SessionLocal
from app.models.models import Booking, Incident
from app.services import email as email_service
from app.services.audit import write_audit

logger = logging.getLogger(__name__)


def process_deadlines(db: Session) -> int:
    """Create incidents/notifications for breached windows. Returns count of new flags."""
    now = datetime.utcnow()
    flagged = 0

    # Missed check-out: keys collected, not yet checked out, deadline passed
    checkout_due = (
        db.query(Booking)
        .options(joinedload(Booking.driver), joinedload(Booking.vehicle))
        .filter(
            Booking.KeyCollected.is_(True),
            Booking.CheckOutTimestamp.is_(None),
            Booking.CheckOutDeadline.isnot(None),
            Booking.CheckOutDeadline < now,
            Booking.MissedCheckoutFlagged.is_(False),
            Booking.BookingStatus.in_(["Approved", "Flagged"]),
        )
        .all()
    )
    for booking in checkout_due:
        booking.MissedCheckoutFlagged = True
        if booking.BookingStatus == "Approved":
            booking.BookingStatus = "Flagged"
        incident = Incident(
            BookingID=booking.BookingID,
            FlagType="Missed Checkout Window",
            RaisedOn=now,
            ReviewStatus="Open",
        )
        db.add(incident)
        db.flush()
        write_audit(
            db,
            table_name="Incidents",
            record_id=incident.IncidentID,
            action="CREATE",
            changed_by=None,
            new_value={"FlagType": "Missed Checkout Window", "BookingID": booking.BookingID},
        )
        write_audit(
            db,
            table_name="Bookings",
            record_id=booking.BookingID,
            action="FLAG_MISSED_CHECKOUT",
            changed_by=None,
            new_value={"BookingStatus": booking.BookingStatus, "MissedCheckoutFlagged": True},
        )
        email_service.notify_missed_checkout(db, booking, booking.driver)
        flagged += 1

    # Overdue return: checked out, not checked in, deadline passed
    checkin_due = (
        db.query(Booking)
        .options(joinedload(Booking.driver), joinedload(Booking.vehicle))
        .filter(
            Booking.CheckOutTimestamp.isnot(None),
            Booking.CheckInTimestamp.is_(None),
            Booking.CheckInDeadline.isnot(None),
            Booking.CheckInDeadline < now,
            Booking.MissedCheckinFlagged.is_(False),
            Booking.BookingStatus.in_(["Checked Out", "Flagged"]),
        )
        .all()
    )
    for booking in checkin_due:
        booking.MissedCheckinFlagged = True
        if booking.BookingStatus == "Checked Out":
            booking.BookingStatus = "Flagged"
        incident = Incident(
            BookingID=booking.BookingID,
            FlagType="Overdue Return",
            RaisedOn=now,
            ReviewStatus="Open",
        )
        db.add(incident)
        db.flush()
        write_audit(
            db,
            table_name="Incidents",
            record_id=incident.IncidentID,
            action="CREATE",
            changed_by=None,
            new_value={"FlagType": "Overdue Return", "BookingID": booking.BookingID},
        )
        write_audit(
            db,
            table_name="Bookings",
            record_id=booking.BookingID,
            action="FLAG_OVERDUE_RETURN",
            changed_by=None,
            new_value={"BookingStatus": booking.BookingStatus, "MissedCheckinFlagged": True},
        )
        email_service.notify_overdue_return(db, booking, booking.driver)
        flagged += 1

    if flagged:
        db.commit()
    return flagged


async def deadline_loop(stop_event: asyncio.Event) -> None:
    logger.info("Deadline scanner started (every %ss)", DEADLINE_CHECK_INTERVAL_SECONDS)
    while not stop_event.is_set():
        try:
            db = SessionLocal()
            try:
                n = process_deadlines(db)
                if n:
                    logger.info("Deadline scanner flagged %s booking(s)", n)
            finally:
                db.close()
        except Exception:
            logger.exception("Deadline scanner error")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=DEADLINE_CHECK_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
