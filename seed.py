"""
Seed / reset the local SQLite database with demo data.

Usage:
  python seed.py --reset
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta

from app.config import DATA_DIR, TRIP_WINDOW_HOURS, UPLOAD_DIR
from app.database import Base, SessionLocal, engine, init_db
from app.models.models import (
    AuditLog,
    Booking,
    Incident,
    NotificationsLog,
    ServiceHistory,
    TrackerData,
    User,
    Vehicle,
)
from app.services import email as email_service
from app.services.audit import write_audit


def _clear_all(db) -> None:
    for table in (
        NotificationsLog,
        AuditLog,
        TrackerData,
        Incident,
        ServiceHistory,
        Booking,
        Vehicle,
        User,
    ):
        db.query(table).delete()
    db.commit()


def _photos(prefix: str) -> str:
    angles = ("front", "back", "left", "right", "odometer")
    return json.dumps([{"angle": a, "path": f"seed/{prefix}/{a}.jpg"} for a in angles])


def _closed_trip(
    *,
    vehicle_id: int,
    driver_id: int,
    approver_id: int,
    start: datetime,
    purpose: str,
    destination: str,
    out_km: int,
    in_km: int,
    booking_type: str = "Immediate",
    hours: float = 3.0,
    damage: str | None = None,
    bay: str = "GFS Basement Bay A1",
) -> Booking:
    """Historical closed booking for analytics / incident demos."""
    duration = timedelta(hours=hours)
    return Booking(
        VehicleID=vehicle_id,
        DriverID=driver_id,
        BookingType=booking_type,
        ReservationStart=start,
        ReservationEnd=start + duration if booking_type == "Advance Reservation" else None,
        PurposeReason=purpose,
        Destination=destination,
        BookingStatus="Closed",
        RequestedAt=start - timedelta(hours=2),
        ApprovedBy=approver_id,
        ApprovalTimestamp=start - timedelta(hours=1),
        KeyCollected=True,
        KeyCollectedTimestamp=start - timedelta(minutes=20),
        KeyReturned=True,
        KeyReturnedTimestamp=start + duration + timedelta(minutes=15),
        CheckOutTimestamp=start,
        CheckOutMileage=out_km,
        CheckOutLocation=bay,
        CheckOutLatitude=-33.9249,
        CheckOutLongitude=18.4241,
        CheckOutPhotoPaths=_photos(f"hist_out_{int(start.timestamp())}"),
        CheckInTimestamp=start + duration,
        CheckInMileage=in_km,
        CheckInLocation=bay,
        CheckInPhotoPaths=_photos(f"hist_in_{int(start.timestamp())}"),
        DamageNoted=bool(damage),
        DamageDescription=damage,
        CheckOutDeadline=start + timedelta(hours=1),
        CheckInDeadline=start + duration,
    )


def seed(reset: bool = False) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    db = SessionLocal()
    try:
        if reset:
            _clear_all(db)
        elif db.query(User).count() > 0:
            print("Database already has data. Use --reset to clear and reseed.")
            return

        now = datetime.utcnow()

        nishen = User(Username="nishen", DisplayName="Nishen Singh", Role="Manager", IsActive=True)
        neo = User(Username="neo", DisplayName="Neo Mwambi", Role="Admin", IsActive=True)
        omphile = User(Username="omphile", DisplayName="Omphile Modiba", Role="Employee", IsActive=True)
        sboniso = User(Username="sboniso", DisplayName="Sboniso Shoba", Role="Employee", IsActive=True)
        faiz = User(Username="faiz", DisplayName="Faiz Hoosen", Role="Employee", IsActive=True)
        karish = User(Username="karish", DisplayName="Karish Ramnarayan", Role="Employee", IsActive=True)
        riyaaz = User(Username="riyaaz", DisplayName="Riyaaz Dadamia", Role="Employee", IsActive=True)
        leon = User(Username="leon", DisplayName="Leon Pottas", Role="Employee", IsActive=True)
        db.add_all([nishen, neo, omphile, sboniso, faiz, karish, riyaaz, leon])
        db.flush()

        v1 = Vehicle(
            RegistrationNumber="CA 123-456",
            MakeModel="Toyota Corolla Quest",
            CurrentStatus="In Use",
            CurrentMileage=45200,
            CurrentParkingLocation="GFS Basement Bay A1",
            ServiceIntervalKm=15000,
            LastServiceMileage=40000,
            ServiceAlertThresholdKm=500,
            LastServiceDate=now - timedelta(days=120),
            NextServiceDueDate=now + timedelta(days=60),
            IsActive=True,
        )
        v2 = Vehicle(
            RegistrationNumber="CA 789-012",
            MakeModel="Volkswagen Polo Vivo",
            CurrentStatus="Reserved",
            CurrentMileage=29850,
            CurrentParkingLocation="GFS Basement Bay A2",
            ServiceIntervalKm=15000,
            LastServiceMileage=15000,
            ServiceAlertThresholdKm=500,  # due at 30000 → 150 km left
            LastServiceDate=now - timedelta(days=200),
            NextServiceDueDate=now + timedelta(days=10),
            IsActive=True,
        )
        # Available for Immediate request / approval testing
        v3 = Vehicle(
            RegistrationNumber="CA 456-789",
            MakeModel="Hyundai Grand i10",
            CurrentStatus="Available",
            CurrentMileage=18200,
            CurrentParkingLocation="GFS Basement Bay A3",
            ServiceIntervalKm=15000,
            LastServiceMileage=15000,
            ServiceAlertThresholdKm=500,
            LastServiceDate=now - timedelta(days=90),
            NextServiceDueDate=now + timedelta(days=90),
            IsActive=True,
        )
        db.add_all([v1, v2, v3])
        db.flush()

        db.add_all(
            [
                ServiceHistory(
                    VehicleID=v1.VehicleID,
                    ServiceDate=now - timedelta(days=120),
                    MileageAtService=40000,
                    ServiceType="Full service",
                    Notes="Oil, filters, brakes checked",
                    LoggedBy=nishen.UserID,
                ),
                ServiceHistory(
                    VehicleID=v1.VehicleID,
                    ServiceDate=now - timedelta(days=400),
                    MileageAtService=25000,
                    ServiceType="Interim service",
                    Notes=None,
                    LoggedBy=neo.UserID,
                ),
                ServiceHistory(
                    VehicleID=v2.VehicleID,
                    ServiceDate=now - timedelta(days=200),
                    MileageAtService=15000,
                    ServiceType="Full service",
                    Notes="Approaching next service interval",
                    LoggedBy=nishen.UserID,
                ),
                ServiceHistory(
                    VehicleID=v3.VehicleID,
                    ServiceDate=now - timedelta(days=90),
                    MileageAtService=15000,
                    ServiceType="Full service",
                    Notes="Ready for pool use",
                    LoggedBy=neo.UserID,
                ),
            ]
        )

        # Pending = Advance Reservation for AFTER Faiz returns (valid while Corolla is In Use)
        b_pending = Booking(
            VehicleID=v1.VehicleID,
            DriverID=omphile.UserID,
            BookingType="Advance Reservation",
            ReservationStart=now + timedelta(days=1),
            ReservationEnd=now + timedelta(days=1, hours=4),
            PurposeReason="Urgent follow-up interview",
            Destination="Wynberg SAPS",
            BookingStatus="Pending Approval",
            RequestedAt=now - timedelta(minutes=40),
        )

        # Approved, awaiting key collection (handover queue for Nishen)
        b_approved = Booking(
            VehicleID=v2.VehicleID,
            DriverID=sboniso.UserID,
            BookingType="Advance Reservation",
            ReservationStart=now - timedelta(hours=1),
            ReservationEnd=now + timedelta(hours=3),
            PurposeReason="Witness interview travel",
            Destination="Bellville Forensic Offices",
            BookingStatus="Approved",
            RequestedAt=now - timedelta(hours=4),
            ApprovedBy=nishen.UserID,
            ApprovalTimestamp=now - timedelta(hours=3),
            KeyCollected=False,
        )

        # Checked Out with past CheckInDeadline (Overdue Return demo)
        b_checkout = Booking(
            VehicleID=v1.VehicleID,
            DriverID=faiz.UserID,
            BookingType="Immediate",
            ReservationStart=now - timedelta(hours=2),
            PurposeReason="Scene attendance - case GFS-2044",
            Destination="Athlone",
            BookingStatus="Checked Out",
            RequestedAt=now - timedelta(hours=3),
            ApprovedBy=nishen.UserID,
            ApprovalTimestamp=now - timedelta(hours=2, minutes=30),
            KeyCollected=True,
            KeyCollectedTimestamp=now - timedelta(hours=2, minutes=15),
            CheckOutTimestamp=now - timedelta(hours=2),
            CheckOutMileage=45200,
            CheckOutLocation="GFS Basement Bay A1",
            CheckOutLatitude=-33.9249,
            CheckOutLongitude=18.4241,
            CheckOutPhotoPaths=_photos("checkout_active"),
            CheckOutDeadline=now - timedelta(hours=1, minutes=15),
            CheckInDeadline=now - timedelta(hours=1),
            MissedCheckinFlagged=False,
        )

        # Closed - normal
        b_closed = Booking(
            VehicleID=v1.VehicleID,
            DriverID=faiz.UserID,
            BookingType="Immediate",
            ReservationStart=now - timedelta(days=5),
            PurposeReason="Evidence transport to archive",
            Destination="GFS Secure Archive, Century City",
            BookingStatus="Closed",
            RequestedAt=now - timedelta(days=5, hours=2),
            ApprovedBy=nishen.UserID,
            ApprovalTimestamp=now - timedelta(days=5, hours=1),
            KeyCollected=True,
            KeyCollectedTimestamp=now - timedelta(days=5, hours=1),
            KeyReturned=True,
            KeyReturnedTimestamp=now - timedelta(days=5) + timedelta(hours=3),
            CheckOutTimestamp=now - timedelta(days=5) + timedelta(minutes=50),
            CheckOutMileage=44800,
            CheckOutLocation="GFS Basement Bay A1",
            CheckOutPhotoPaths=_photos("closed_out"),
            CheckInTimestamp=now - timedelta(days=5) + timedelta(hours=2, minutes=30),
            CheckInMileage=44920,
            CheckInLocation="GFS Basement Bay A1",
            CheckInPhotoPaths=_photos("closed_in"),
            DamageNoted=False,
        )

        # Closed - damage
        b_damage = Booking(
            VehicleID=v2.VehicleID,
            DriverID=omphile.UserID,
            BookingType="Immediate",
            ReservationStart=now - timedelta(days=12),
            PurposeReason="Field verification - insurance claim",
            Destination="Mitchells Plain",
            BookingStatus="Closed",
            RequestedAt=now - timedelta(days=12, hours=1),
            ApprovedBy=nishen.UserID,
            ApprovalTimestamp=now - timedelta(days=12),
            KeyCollected=True,
            KeyCollectedTimestamp=now - timedelta(days=12),
            KeyReturned=True,
            KeyReturnedTimestamp=now - timedelta(days=12) + timedelta(hours=4),
            CheckOutTimestamp=now - timedelta(days=12) + timedelta(minutes=40),
            CheckOutMileage=29100,
            CheckOutLocation="GFS Basement Bay A2",
            CheckOutPhotoPaths=_photos("damage_out"),
            CheckInTimestamp=now - timedelta(days=12) + timedelta(hours=3),
            CheckInMileage=29240,
            CheckInLocation="GFS Basement Bay A2",
            CheckInPhotoPaths=_photos("damage_in"),
            DamageNoted=True,
            DamageDescription="Scratch on rear bumper, passenger side",
        )

        # Rejected
        b_rejected = Booking(
            VehicleID=v1.VehicleID,
            DriverID=sboniso.UserID,
            BookingType="Advance Reservation",
            ReservationStart=now - timedelta(days=2),
            ReservationEnd=now - timedelta(days=2) + timedelta(hours=4),
            PurposeReason="Personal errand",
            Destination="Canal Walk",
            BookingStatus="Rejected",
            RequestedAt=now - timedelta(days=2, hours=3),
            ApprovedBy=nishen.UserID,
            ApprovalTimestamp=now - timedelta(days=2, hours=2),
            RejectionReason="Not a business-related purpose",
        )

        # --- Historical closed trips (approx. last 6 months) for analytics ---
        hist_specs = [
            # (days_ago, hours, driver, vehicle, out, in, type, purpose, dest, damage?)
            (175, 2.5, omphile, v1, 41000, 41085, "Immediate", "Scene attendance - GFS-1881", "Athlone", None),
            (168, 4.0, sboniso, v2, 27100, 27240, "Advance Reservation", "Witness interview", "Bellville", None),
            (160, 3.0, faiz, v1, 41100, 41220, "Immediate", "Evidence transport", "Century City", None),
            (152, 5.0, karish, v3, 16000, 16180, "Immediate", "Insurance verification", "Mitchells Plain", "Front bumper scuff from parking pillar"),
            (145, 2.0, riyaaz, v2, 27300, 27390, "Immediate", "Follow-up statement", "Wynberg SAPS", None),
            (138, 6.0, leon, v1, 41300, 41510, "Advance Reservation", "Multi-site enquiry", "Khayelitsha", None),
            (130, 3.5, omphile, v3, 16200, 16340, "Immediate", "Document collection", "Cape Town CBD", None),
            (122, 2.0, sboniso, v1, 41600, 41670, "Immediate", "Court attendance support", "Cape Town High Court", None),
            (115, 4.0, faiz, v2, 27500, 27680, "Advance Reservation", "Field verification - Parow claim", "Parow", None),
            (108, 3.0, karish, v1, 41700, 41820, "Immediate", "Scene attendance - GFS-1910", "Gugulethu", None),
            (100, 2.5, riyaaz, v3, 16400, 16495, "Immediate", "Archive drop-off", "Century City", None),
            (92, 5.0, leon, v2, 27750, 27940, "Immediate", "Regional liaison", "Stellenbosch", "Side mirror crack - passenger side"),
            (85, 3.0, omphile, v1, 42000, 42110, "Advance Reservation", "Interview travel", "Bellville", None),
            (78, 2.0, sboniso, v3, 16550, 16620, "Immediate", "Urgent courier to lab", "Tygerberg", None),
            (70, 4.5, faiz, v1, 42200, 42380, "Immediate", "Scene attendance - GFS-1966", "Langa", None),
            (63, 3.0, karish, v2, 28100, 28220, "Advance Reservation", "Witness statement", "Athlone", None),
            (55, 2.5, riyaaz, v1, 42500, 42590, "Immediate", "Evidence to archive", "Century City", None),
            (48, 6.0, leon, v3, 16800, 17040, "Immediate", "Multi-stop enquiry", "Khayelitsha / Mitchells Plain", None),
            (42, 3.0, omphile, v2, 28400, 28510, "Immediate", "Insurance claim visit", "Goodwood", "Rear bumper scratch, passenger side"),
            (35, 2.0, sboniso, v1, 43000, 43075, "Advance Reservation", "Court documents", "Cape Town CBD", None),
            (28, 4.0, faiz, v3, 17200, 17350, "Immediate", "Field verification - Delft claim", "Delft", None),
            (22, 3.5, karish, v2, 28700, 28840, "Immediate", "Scene attendance - GFS-2012", "Nyanga", None),
            (18, 2.5, riyaaz, v1, 43500, 43600, "Immediate", "Lab sample transfer", "Tygerberg", None),
            (14, 5.0, leon, v3, 17500, 17720, "Advance Reservation", "Regional follow-up", "Paarl", None),
            (10, 3.0, omphile, v2, 28900, 29020, "Immediate", "Witness interview", "Wynberg", None),
            (7, 2.0, sboniso, v1, 44000, 44080, "Immediate", "Document delivery", "GFS Secure Archive, Century City", None),
            (3, 4.0, faiz, v3, 17850, 18020, "Immediate", "Scene attendance - GFS-2038", "Philippi", None),
        ]

        hist_bookings: list[Booking] = []
        for days_ago, hours, driver, vehicle, out_km, in_km, btype, purpose, dest, damage in hist_specs:
            bay = (
                "GFS Basement Bay A1"
                if vehicle is v1
                else "GFS Basement Bay A2"
                if vehicle is v2
                else "GFS Basement Bay A3"
            )
            hist_bookings.append(
                _closed_trip(
                    vehicle_id=vehicle.VehicleID,
                    driver_id=driver.UserID,
                    approver_id=nishen.UserID if days_ago % 3 else neo.UserID,
                    start=now - timedelta(days=days_ago, hours=9),
                    purpose=purpose,
                    destination=dest,
                    out_km=out_km,
                    in_km=in_km,
                    booking_type=btype,
                    hours=hours,
                    damage=damage,
                    bay=bay,
                )
            )

        # Extra cancelled / rejected for status mix in analytics
        b_cancelled = Booking(
            VehicleID=v3.VehicleID,
            DriverID=karish.UserID,
            BookingType="Advance Reservation",
            ReservationStart=now - timedelta(days=20),
            ReservationEnd=now - timedelta(days=20) + timedelta(hours=3),
            PurposeReason="Site visit cancelled by requester",
            Destination="Bellville",
            BookingStatus="Cancelled",
            RequestedAt=now - timedelta(days=21),
            ApprovedBy=None,
        )
        b_rejected2 = Booking(
            VehicleID=v2.VehicleID,
            DriverID=leon.UserID,
            BookingType="Immediate",
            ReservationStart=now - timedelta(days=9),
            PurposeReason="Weekend personal use",
            Destination="Waterfront",
            BookingStatus="Rejected",
            RequestedAt=now - timedelta(days=9, hours=2),
            ApprovedBy=nishen.UserID,
            ApprovalTimestamp=now - timedelta(days=9, hours=1),
            RejectionReason="Pool vehicles are for official GFS duties only",
        )

        db.add_all(
            [b_pending, b_approved, b_checkout, b_closed, b_damage, b_rejected, b_cancelled, b_rejected2]
            + hist_bookings
        )
        db.flush()

        # Index helpful historical bookings for incidents
        by_purpose = {b.PurposeReason: b for b in hist_bookings}

        incidents = [
            Incident(
                BookingID=b_damage.BookingID,
                FlagType="Damage",
                RaisedOn=b_damage.CheckInTimestamp,
                ReviewedBy=nishen.UserID,
                ReviewStatus="Resolved",
                ResolutionNotes="Scratch logged with facilities; driver acknowledged.",
            ),
            Incident(
                BookingID=by_purpose["Insurance verification"].BookingID,
                FlagType="Damage",
                RaisedOn=by_purpose["Insurance verification"].CheckInTimestamp,
                ReviewedBy=nishen.UserID,
                ReviewStatus="Resolved",
                ResolutionNotes="Minor scuff - no claim raised. Photos retained.",
            ),
            Incident(
                BookingID=by_purpose["Regional liaison"].BookingID,
                FlagType="Damage",
                RaisedOn=by_purpose["Regional liaison"].CheckInTimestamp,
                ReviewedBy=neo.UserID,
                ReviewStatus="Resolved",
                ResolutionNotes="Mirror replaced via fleet workshop. Cost coded to GFS.",
            ),
            Incident(
                BookingID=by_purpose["Insurance claim visit"].BookingID,
                FlagType="Damage",
                RaisedOn=by_purpose["Insurance claim visit"].CheckInTimestamp,
                ReviewedBy=None,
                ReviewStatus="Under Review",
                ResolutionNotes=None,
            ),
            Incident(
                BookingID=by_purpose["Scene attendance - GFS-1910"].BookingID,
                FlagType="Missed Checkout Window",
                RaisedOn=by_purpose["Scene attendance - GFS-1910"].CheckOutTimestamp + timedelta(hours=1, minutes=20),
                ReviewedBy=nishen.UserID,
                ReviewStatus="Resolved",
                ResolutionNotes="Driver delayed at scene; verbal counselling recorded.",
            ),
            Incident(
                BookingID=by_purpose["Multi-site enquiry"].BookingID,
                FlagType="Overdue Return",
                RaisedOn=by_purpose["Multi-site enquiry"].CheckInDeadline + timedelta(minutes=40),
                ReviewedBy=nishen.UserID,
                ReviewStatus="Resolved",
                ResolutionNotes="Traffic delay on N2. Accepted with note on file.",
            ),
            Incident(
                BookingID=by_purpose["Field verification - Parow claim"].BookingID,
                FlagType="Missed Checkout Window",
                RaisedOn=by_purpose["Field verification - Parow claim"].CheckOutTimestamp
                + timedelta(hours=1, minutes=10),
                ReviewedBy=neo.UserID,
                ReviewStatus="Resolved",
                ResolutionNotes="Key handover ran late; process reminder sent to manager.",
            ),
            Incident(
                BookingID=by_purpose["Scene attendance - GFS-1966"].BookingID,
                FlagType="Overdue Return",
                RaisedOn=by_purpose["Scene attendance - GFS-1966"].CheckInDeadline + timedelta(hours=1),
                ReviewedBy=nishen.UserID,
                ReviewStatus="Resolved",
                ResolutionNotes="Extended scene work authorised retrospectively.",
            ),
            Incident(
                BookingID=by_purpose["Multi-stop enquiry"].BookingID,
                FlagType="Missed Checkout Window",
                RaisedOn=by_purpose["Multi-stop enquiry"].CheckOutTimestamp + timedelta(hours=1, minutes=5),
                ReviewedBy=None,
                ReviewStatus="Open",
                ResolutionNotes=None,
            ),
            Incident(
                BookingID=by_purpose["Scene attendance - GFS-2012"].BookingID,
                FlagType="Overdue Return",
                RaisedOn=by_purpose["Scene attendance - GFS-2012"].CheckInDeadline + timedelta(minutes=50),
                ReviewedBy=nishen.UserID,
                ReviewStatus="Under Review",
                ResolutionNotes="Awaiting driver written explanation.",
            ),
            Incident(
                BookingID=by_purpose["Regional follow-up"].BookingID,
                FlagType="Damage at Check-Out",
                RaisedOn=by_purpose["Regional follow-up"].CheckOutTimestamp,
                ReviewedBy=neo.UserID,
                ReviewStatus="Resolved",
                ResolutionNotes="Pre-existing dent noted at check-out; not attributed to this trip.",
            ),
            Incident(
                BookingID=by_purpose["Lab sample transfer"].BookingID,
                FlagType="Missed Checkout Window",
                RaisedOn=by_purpose["Lab sample transfer"].CheckOutTimestamp + timedelta(hours=1, minutes=30),
                ReviewedBy=None,
                ReviewStatus="Open",
                ResolutionNotes=None,
            ),
            Incident(
                BookingID=by_purpose["Scene attendance - GFS-2038"].BookingID,
                FlagType="Overdue Return",
                RaisedOn=by_purpose["Scene attendance - GFS-2038"].CheckInDeadline + timedelta(hours=2),
                ReviewedBy=None,
                ReviewStatus="Open",
                ResolutionNotes=None,
            ),
            Incident(
                BookingID=b_closed.BookingID,
                FlagType="Missed Checkout Window",
                RaisedOn=b_closed.CheckOutTimestamp + timedelta(minutes=70) if b_closed.CheckOutTimestamp else now,
                ReviewedBy=nishen.UserID,
                ReviewStatus="Resolved",
                ResolutionNotes="Minor delay collecting keys; no further action.",
            ),
        ]
        db.add_all(incidents)

        email_service.log_notification(
            db,
            booking_id=b_pending.BookingID,
            recipient_role="Manager",
            recipient_name=nishen.DisplayName,
            email_type="BookingRequest",
            subject=f"[GFS Vehicles] New booking request - {v1.RegistrationNumber}",
            body=(
                f"Hello,\n\n{omphile.DisplayName} has requested {v1.MakeModel} ({v1.RegistrationNumber}).\n"
                f"Purpose: {b_pending.PurposeReason}\nDestination: {b_pending.Destination}\n\n"
                f"Please review and approve or reject in the Admin portal:\n"
                f"  /admin/approvals.html\n"
            ),
            changed_by=omphile.UserID,
        )
        email_service.log_notification(
            db,
            booking_id=b_approved.BookingID,
            recipient_role="Employee",
            recipient_name=sboniso.DisplayName,
            email_type="BookingApproved",
            subject=f"[GFS Vehicles] Booking approved - {v2.RegistrationNumber}",
            body=(
                f"Hello {sboniso.DisplayName},\n\n"
                f"Your booking was approved by {nishen.DisplayName}. "
                f"Collect the keys in person from {nishen.DisplayName}.\n"
            ),
            changed_by=nishen.UserID,
        )

        write_audit(
            db,
            table_name="System",
            record_id=0,
            action="SEED",
            changed_by=neo.UserID,
            new_value={"message": "Database seeded with demo data", "at": now.isoformat()},
        )
        db.commit()

        print("Seed complete.")
        print(
            "  Users: omphile, sboniso, faiz, karish, riyaaz, leon (Employee); "
            "nishen (Manager); neo (Admin)"
        )
        print(
            f"  Vehicles: {v1.RegistrationNumber} (In Use), "
            f"{v2.RegistrationNumber} (Reserved, near service), "
            f"{v3.RegistrationNumber} (Available)"
        )
        print(
            f"  History: {len(hist_bookings) + 2} closed trips + {len(incidents)} incidents "
            f"for Analytics / Incidents demos"
        )
        print(f"  Trip window: {TRIP_WINDOW_HOURS}h - deadline scanner flags missed windows after startup")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed GFS Vehicle Management demo data")
    parser.add_argument("--reset", action="store_true", help="Clear all tables and reseed")
    args = parser.parse_args()
    if args.reset:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
    seed(reset=args.reset)


if __name__ == "__main__":
    main()
