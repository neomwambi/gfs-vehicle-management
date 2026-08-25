"""Email notification service (simulated).

Prototype: writes to NotificationsLog only. Later swap for Graph API / SMTP.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.models import Booking, NotificationsLog, User
from app.services.audit import write_audit


def _managers(db: Session) -> list[User]:
    return (
        db.query(User)
        .filter(User.IsActive.is_(True), User.Role.in_(["Manager", "Admin"]))
        .all()
    )


def log_notification(
    db: Session,
    *,
    booking_id: int | None,
    recipient_role: str,
    recipient_name: str,
    email_type: str,
    subject: str,
    body: str,
    approval_token: str | None = None,
    changed_by: int | None = None,
) -> NotificationsLog:
    row = NotificationsLog(
        BookingID=booking_id,
        RecipientRole=recipient_role,
        RecipientName=recipient_name,
        EmailType=email_type,
        SentAt=datetime.utcnow(),
        Subject=subject,
        Body=body,
        ApprovalToken=approval_token,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        table_name="NotificationsLog",
        record_id=row.NotificationID,
        action="CREATE",
        changed_by=changed_by,
        new_value={"EmailType": email_type, "Subject": subject, "Recipient": recipient_name},
    )
    return row


def notify_managers_new_request(db: Session, booking: Booking, driver: User) -> None:
    vehicle = booking.vehicle
    link = "/admin/approvals.html"
    subject = f"[GFS Vehicles] New booking request - {vehicle.RegistrationNumber}"
    body = (
        f"Hello,\n\n"
        f"{driver.DisplayName} has requested {vehicle.MakeModel} ({vehicle.RegistrationNumber}).\n\n"
        f"Purpose: {booking.PurposeReason}\n"
        f"Destination: {booking.Destination}\n"
        f"Type: {booking.BookingType}\n"
        f"Start: {booking.ReservationStart}\n\n"
        f"Please review and approve or reject in the Admin portal:\n"
        f"  {link}\n\n"
        f"- GFS Vehicle Management (simulated email)\n"
    )
    for mgr in _managers(db):
        log_notification(
            db,
            booking_id=booking.BookingID,
            recipient_role=mgr.Role,
            recipient_name=mgr.DisplayName,
            email_type="BookingRequest",
            subject=subject,
            body=body,
            changed_by=driver.UserID,
        )


def notify_employee_decision(
    db: Session,
    booking: Booking,
    driver: User,
    approved: bool,
    approver: User,
) -> None:
    vehicle = booking.vehicle
    if approved:
        subject = f"[GFS Vehicles] Booking approved - {vehicle.RegistrationNumber}"
        body = (
            f"Hello {driver.DisplayName},\n\n"
            f"Your request for {vehicle.MakeModel} ({vehicle.RegistrationNumber}) was APPROVED "
            f"by {approver.DisplayName}.\n\n"
            f"Please collect the keys in person from {approver.DisplayName}. "
            f"They must confirm key handover in the app before you can check out the vehicle.\n\n"
            f"- GFS Vehicle Management (simulated email)\n"
        )
        email_type = "BookingApproved"
    else:
        subject = f"[GFS Vehicles] Booking rejected - {vehicle.RegistrationNumber}"
        body = (
            f"Hello {driver.DisplayName},\n\n"
            f"Your request for {vehicle.MakeModel} ({vehicle.RegistrationNumber}) was REJECTED "
            f"by {approver.DisplayName}.\n\n"
            f"Reason: {booking.RejectionReason or 'Not provided'}\n\n"
            f"- GFS Vehicle Management (simulated email)\n"
        )
        email_type = "BookingRejected"

    log_notification(
        db,
        booking_id=booking.BookingID,
        recipient_role=driver.Role,
        recipient_name=driver.DisplayName,
        email_type=email_type,
        subject=subject,
        body=body,
        changed_by=approver.UserID,
    )


def notify_managers_checkin_complete(db: Session, booking: Booking, driver: User) -> None:
    vehicle = booking.vehicle
    subject = f"[GFS Vehicles] Vehicle returned - key expected - {vehicle.RegistrationNumber}"
    body = (
        f"Hello,\n\n"
        f"{driver.DisplayName} has completed check-in for {vehicle.MakeModel} "
        f"({vehicle.RegistrationNumber}).\n\n"
        f"The physical key is expected back within the next hour. "
        f"Please confirm key return in the Admin portal.\n\n"
        f"Damage noted: {'YES - ' + (booking.DamageDescription or '') if booking.DamageNoted else 'No'}\n\n"
        f"- GFS Vehicle Management (simulated email)\n"
    )
    for mgr in _managers(db):
        log_notification(
            db,
            booking_id=booking.BookingID,
            recipient_role=mgr.Role,
            recipient_name=mgr.DisplayName,
            email_type="CheckInComplete",
            subject=subject,
            body=body,
            changed_by=driver.UserID,
        )


def notify_missed_checkout(db: Session, booking: Booking, driver: User) -> None:
    vehicle = booking.vehicle
    subject = f"[GFS Vehicles] Missed check-out window - {vehicle.RegistrationNumber}"
    body_employee = (
        f"Hello {driver.DisplayName},\n\n"
        f"You collected keys for {vehicle.RegistrationNumber} but did not complete check-out "
        f"before the deadline ({booking.CheckOutDeadline}). An incident has been raised for review.\n\n"
        f"Please complete check-out as soon as possible.\n\n"
        f"- GFS Vehicle Management (simulated email)\n"
    )
    body_manager = (
        f"Hello,\n\n"
        f"{driver.DisplayName} missed the check-out window for {vehicle.RegistrationNumber}.\n"
        f"Deadline was {booking.CheckOutDeadline}. An incident (Missed Checkout Window) is open.\n\n"
        f"- GFS Vehicle Management (simulated email)\n"
    )
    log_notification(
        db,
        booking_id=booking.BookingID,
        recipient_role=driver.Role,
        recipient_name=driver.DisplayName,
        email_type="MissedCheckout",
        subject=subject,
        body=body_employee,
    )
    for mgr in _managers(db):
        log_notification(
            db,
            booking_id=booking.BookingID,
            recipient_role=mgr.Role,
            recipient_name=mgr.DisplayName,
            email_type="MissedCheckout",
            subject=subject,
            body=body_manager,
        )


def notify_overdue_return(db: Session, booking: Booking, driver: User) -> None:
    vehicle = booking.vehicle
    subject = f"[GFS Vehicles] Overdue return - {vehicle.RegistrationNumber}"
    body = (
        f"Hello,\n\n"
        f"{driver.DisplayName} has not completed check-in for {vehicle.RegistrationNumber} "
        f"before the deadline ({booking.CheckInDeadline}). "
        f"An incident (Overdue Return) has been raised.\n\n"
        f"- GFS Vehicle Management (simulated email)\n"
    )
    for mgr in _managers(db):
        log_notification(
            db,
            booking_id=booking.BookingID,
            recipient_role=mgr.Role,
            recipient_name=mgr.DisplayName,
            email_type="OverdueReturn",
            subject=subject,
            body=body,
        )


def notify_damage_reported(
    db: Session, booking: Booking, driver: User, *, phase: str = "check-in"
) -> None:
    vehicle = booking.vehicle
    phase_label = "check-out" if phase == "check-out" else "check-in"
    subject = f"[GFS Vehicles] Damage reported - {vehicle.RegistrationNumber}"
    body = (
        f"Hello,\n\n"
        f"{driver.DisplayName} reported damage on {phase_label} for {vehicle.RegistrationNumber}.\n\n"
        f"Description: {booking.DamageDescription}\n\n"
        f"Please review the incident in the Admin portal.\n\n"
        f"- GFS Vehicle Management (simulated email)\n"
    )
    for mgr in _managers(db):
        log_notification(
            db,
            booking_id=booking.BookingID,
            recipient_role=mgr.Role,
            recipient_name=mgr.DisplayName,
            email_type="DamageReported",
            subject=subject,
            body=body,
            changed_by=driver.UserID,
        )
