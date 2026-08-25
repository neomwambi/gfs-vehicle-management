"""Pydantic request/response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import REQUIRED_PHOTO_ANGLES, REQUIRED_PHOTO_COUNT


class UserOut(BaseModel):
    UserID: int
    Username: str
    DisplayName: str
    Role: str

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    Username: str


class LoginResponse(BaseModel):
    session_token: str
    user: UserOut


class VehicleCreate(BaseModel):
    RegistrationNumber: str = Field(min_length=1, max_length=32)
    MakeModel: str = Field(min_length=1, max_length=128)
    CurrentMileage: int = Field(ge=0)
    CurrentParkingLocation: str = Field(min_length=1)
    ServiceIntervalKm: int = Field(gt=0, default=15000)
    LastServiceMileage: int = Field(ge=0, default=0)
    ServiceAlertThresholdKm: int = Field(gt=0, default=500)
    LastServiceDate: datetime | None = None
    NextServiceDueDate: datetime | None = None


class VehicleOut(BaseModel):
    VehicleID: int
    RegistrationNumber: str
    MakeModel: str
    CurrentStatus: str
    CurrentMileage: int
    CurrentParkingLocation: str
    ServiceIntervalKm: int
    LastServiceMileage: int
    ServiceAlertThresholdKm: int
    LastServiceDate: datetime | None
    NextServiceDueDate: datetime | None
    IsActive: bool
    ServiceDueSoon: bool = False
    KmUntilService: int | None = None
    CurrentDriverName: str | None = None
    CurrentBookingID: int | None = None

    model_config = {"from_attributes": True}


class BookingRequestCreate(BaseModel):
    VehicleID: int
    BookingType: Literal["Immediate", "Advance Reservation"]
    ReservationStart: datetime | None = None
    ReservationEnd: datetime | None = None
    PurposeReason: str = Field(min_length=1)
    Destination: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_reservation(self):
        if not self.PurposeReason.strip():
            raise ValueError("PurposeReason is required")
        if not self.Destination.strip():
            raise ValueError("Destination is required")
        if self.BookingType == "Advance Reservation":
            if self.ReservationStart is None or self.ReservationEnd is None:
                raise ValueError("Advance Reservation requires ReservationStart and ReservationEnd")
            if self.ReservationEnd <= self.ReservationStart:
                raise ValueError("ReservationEnd must be after ReservationStart")
        return self


class BookingDecision(BaseModel):
    Decision: Literal["Approve", "Reject"]
    RejectionReason: str | None = None

    @model_validator(mode="after")
    def reject_needs_reason(self):
        if self.Decision == "Reject" and not (self.RejectionReason or "").strip():
            raise ValueError("RejectionReason is required when rejecting")
        return self


class PhotoPayload(BaseModel):
    angle: Literal["front", "back", "left", "right", "odometer"]
    data_url: str = Field(min_length=1)


class CheckOutRequest(BaseModel):
    Mileage: int = Field(ge=0)
    LocationText: str = Field(min_length=1)
    Latitude: float | None = None
    Longitude: float | None = None
    Photos: list[PhotoPayload]
    DamageNoted: bool = False
    DamageDescription: str | None = None

    @field_validator("Photos")
    @classmethod
    def exactly_five_angles(cls, photos: list[PhotoPayload]) -> list[PhotoPayload]:
        if len(photos) != REQUIRED_PHOTO_COUNT:
            raise ValueError(f"Exactly {REQUIRED_PHOTO_COUNT} photos are required")
        angles = {p.angle for p in photos}
        missing = set(REQUIRED_PHOTO_ANGLES) - angles
        if missing:
            raise ValueError(f"Missing photo angles: {', '.join(sorted(missing))}")
        return photos

    @model_validator(mode="after")
    def damage_requires_description(self):
        if self.DamageNoted and not (self.DamageDescription or "").strip():
            raise ValueError("DamageDescription is required when DamageNoted is true")
        return self


class CheckInRequest(BaseModel):
    Mileage: int = Field(ge=0)
    LocationText: str = Field(min_length=1)
    Latitude: float | None = None
    Longitude: float | None = None
    Photos: list[PhotoPayload]
    DamageNoted: bool = False
    DamageDescription: str | None = None

    @field_validator("Photos")
    @classmethod
    def exactly_five_angles(cls, photos: list[PhotoPayload]) -> list[PhotoPayload]:
        if len(photos) != REQUIRED_PHOTO_COUNT:
            raise ValueError(f"Exactly {REQUIRED_PHOTO_COUNT} photos are required")
        angles = {p.angle for p in photos}
        missing = set(REQUIRED_PHOTO_ANGLES) - angles
        if missing:
            raise ValueError(f"Missing photo angles: {', '.join(sorted(missing))}")
        return photos

    @model_validator(mode="after")
    def damage_requires_description(self):
        if self.DamageNoted and not (self.DamageDescription or "").strip():
            raise ValueError("DamageDescription is required when DamageNoted is true")
        return self


class BookingOut(BaseModel):
    BookingID: int
    VehicleID: int
    DriverID: int
    DriverName: str | None = None
    VehicleReg: str | None = None
    VehicleMakeModel: str | None = None
    VehicleCurrentStatus: str | None = None
    BookingType: str
    ReservationStart: datetime
    ReservationEnd: datetime | None
    PurposeReason: str
    Destination: str
    BookingStatus: str
    RequestedAt: datetime
    ApprovedBy: int | None
    ApproverName: str | None = None
    ApprovalTimestamp: datetime | None
    RejectionReason: str | None
    KeyCollected: bool
    KeyCollectedTimestamp: datetime | None
    KeyReturned: bool
    KeyReturnedTimestamp: datetime | None
    CheckOutTimestamp: datetime | None
    CheckOutMileage: int | None
    CheckOutLocation: str | None
    CheckInTimestamp: datetime | None
    CheckInMileage: int | None
    CheckInLocation: str | None
    DamageNoted: bool
    DamageDescription: str | None
    CheckOutDeadline: datetime | None
    CheckInDeadline: datetime | None
    BorrowingRecordScore: int | None = None
    BorrowingRecordLabel: str | None = None
    CanApproveNow: bool = True
    ApproveBlockedReason: str | None = None

    model_config = {"from_attributes": True}


class IncidentOut(BaseModel):
    IncidentID: int
    BookingID: int
    FlagType: str
    RaisedOn: datetime
    ReviewedBy: int | None
    ReviewStatus: str
    ResolutionNotes: str | None
    DriverName: str | None = None
    VehicleReg: str | None = None

    model_config = {"from_attributes": True}


class IncidentReview(BaseModel):
    ReviewStatus: Literal["Open", "Under Review", "Resolved"]
    ResolutionNotes: str | None = None


class NotificationOut(BaseModel):
    NotificationID: int
    BookingID: int | None
    RecipientRole: str
    RecipientName: str
    EmailType: str
    SentAt: datetime
    Subject: str
    Body: str
    ApprovalToken: str | None

    model_config = {"from_attributes": True}


class AuditLogOut(BaseModel):
    LogID: int
    TableName: str
    RecordID: int
    Action: str
    ChangedBy: int | None
    ChangedByName: str | None = None
    ChangedAt: datetime
    OldValue: str | None
    NewValue: str | None

    model_config = {"from_attributes": True}


class ServiceHistoryOut(BaseModel):
    ServiceID: int
    VehicleID: int
    ServiceDate: datetime
    MileageAtService: int
    ServiceType: str
    Notes: str | None
    LoggedBy: int

    model_config = {"from_attributes": True}


class DashboardOut(BaseModel):
    OpenIncidents: int
    VehiclesNearingService: int
    ActiveTrips: int
    MissedWindows: int
    PendingApprovals: int
    AwaitingKeyHandover: int
    AwaitingKeyReturn: int


class MessageOut(BaseModel):
    message: str
    detail: str | None = None
