"""SQLAlchemy ORM models."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "Users"

    UserID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    Username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    DisplayName: Mapped[str] = mapped_column(String(128), nullable=False)
    Role: Mapped[str] = mapped_column(String(32), nullable=False)  # Employee | Manager | Admin
    IsActive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    bookings = relationship("Booking", back_populates="driver", foreign_keys="Booking.DriverID")


class Vehicle(Base):
    __tablename__ = "Vehicles"

    VehicleID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    RegistrationNumber: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    MakeModel: Mapped[str] = mapped_column(String(128), nullable=False)
    CurrentStatus: Mapped[str] = mapped_column(String(32), nullable=False, default="Available")
    # Available | Reserved | In Use
    CurrentMileage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    CurrentParkingLocation: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    ServiceIntervalKm: Mapped[int] = mapped_column(Integer, nullable=False, default=15000)
    LastServiceMileage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ServiceAlertThresholdKm: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    LastServiceDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    NextServiceDueDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    IsActive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    bookings = relationship("Booking", back_populates="vehicle")
    service_history = relationship("ServiceHistory", back_populates="vehicle")


class Booking(Base):
    __tablename__ = "Bookings"

    BookingID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    VehicleID: Mapped[int] = mapped_column(ForeignKey("Vehicles.VehicleID"), nullable=False)
    DriverID: Mapped[int] = mapped_column(ForeignKey("Users.UserID"), nullable=False)
    BookingType: Mapped[str] = mapped_column(String(64), nullable=False)
    # Immediate | Advance Reservation
    ReservationStart: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ReservationEnd: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    PurposeReason: Mapped[str] = mapped_column(Text, nullable=False)
    Destination: Mapped[str] = mapped_column(String(256), nullable=False)
    BookingStatus: Mapped[str] = mapped_column(String(64), nullable=False, default="Pending Approval")
    # Pending Approval | Approved | Rejected | Checked Out | Checked In | Flagged | Closed | Cancelled
    RequestedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    ApprovedBy: Mapped[int | None] = mapped_column(ForeignKey("Users.UserID"), nullable=True)
    ApprovalTimestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    RejectionReason: Mapped[str | None] = mapped_column(Text, nullable=True)

    KeyCollected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    KeyCollectedTimestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    KeyReturned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    KeyReturnedTimestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    CheckOutTimestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    CheckOutMileage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    CheckOutLocation: Mapped[str | None] = mapped_column(String(256), nullable=True)
    CheckOutLatitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    CheckOutLongitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    CheckOutPhotoPaths: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list

    CheckInTimestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    CheckInMileage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    CheckInLocation: Mapped[str | None] = mapped_column(String(256), nullable=True)
    CheckInLatitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    CheckInLongitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    CheckInPhotoPaths: Mapped[str | None] = mapped_column(Text, nullable=True)

    DamageNoted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    DamageDescription: Mapped[str | None] = mapped_column(Text, nullable=True)

    CheckOutDeadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    CheckInDeadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    MissedCheckoutFlagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    MissedCheckinFlagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    vehicle = relationship("Vehicle", back_populates="bookings")
    driver = relationship("User", back_populates="bookings", foreign_keys=[DriverID])
    approver = relationship("User", foreign_keys=[ApprovedBy])
    incidents = relationship("Incident", back_populates="booking")


class Incident(Base):
    __tablename__ = "Incidents"

    IncidentID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    BookingID: Mapped[int] = mapped_column(ForeignKey("Bookings.BookingID"), nullable=False)
    FlagType: Mapped[str] = mapped_column(String(128), nullable=False)
    RaisedOn: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    ReviewedBy: Mapped[int | None] = mapped_column(ForeignKey("Users.UserID"), nullable=True)
    ReviewStatus: Mapped[str] = mapped_column(String(64), nullable=False, default="Open")
    ResolutionNotes: Mapped[str | None] = mapped_column(Text, nullable=True)

    booking = relationship("Booking", back_populates="incidents")


class ServiceHistory(Base):
    __tablename__ = "ServiceHistory"

    ServiceID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    VehicleID: Mapped[int] = mapped_column(ForeignKey("Vehicles.VehicleID"), nullable=False)
    ServiceDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    MileageAtService: Mapped[int] = mapped_column(Integer, nullable=False)
    ServiceType: Mapped[str] = mapped_column(String(128), nullable=False)
    Notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    LoggedBy: Mapped[int] = mapped_column(ForeignKey("Users.UserID"), nullable=False)

    vehicle = relationship("Vehicle", back_populates="service_history")


class TrackerData(Base):
    """Reserved for a future GPS tracker phase - unused in the prototype."""

    __tablename__ = "TrackerData"

    TrackerID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    BookingID: Mapped[int] = mapped_column(ForeignKey("Bookings.BookingID"), nullable=False)
    TrackedRoute: Mapped[str | None] = mapped_column(Text, nullable=True)
    TrackedStartLocation: Mapped[str | None] = mapped_column(String(256), nullable=True)
    TrackedEndLocation: Mapped[str | None] = mapped_column(String(256), nullable=True)
    LocationMatch: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class AuditLog(Base):
    __tablename__ = "AuditLog"

    LogID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    TableName: Mapped[str] = mapped_column(String(64), nullable=False)
    RecordID: Mapped[int] = mapped_column(Integer, nullable=False)
    Action: Mapped[str] = mapped_column(String(64), nullable=False)
    ChangedBy: Mapped[int | None] = mapped_column(ForeignKey("Users.UserID"), nullable=True)
    ChangedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    OldValue: Mapped[str | None] = mapped_column(Text, nullable=True)
    NewValue: Mapped[str | None] = mapped_column(Text, nullable=True)


class NotificationsLog(Base):
    __tablename__ = "NotificationsLog"

    NotificationID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    BookingID: Mapped[int | None] = mapped_column(ForeignKey("Bookings.BookingID"), nullable=True)
    RecipientRole: Mapped[str] = mapped_column(String(32), nullable=False)
    RecipientName: Mapped[str] = mapped_column(String(128), nullable=False)
    EmailType: Mapped[str] = mapped_column(String(64), nullable=False)
    SentAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    Subject: Mapped[str] = mapped_column(String(512), nullable=False)
    Body: Mapped[str] = mapped_column(Text, nullable=False)
    ApprovalToken: Mapped[str | None] = mapped_column(String(128), nullable=True)
