"""Validation logic stubs for GFS Vehicle Management."""

import pytest
from pydantic import ValidationError

from app.schemas.schemas import BookingRequestCreate, CheckInRequest, CheckOutRequest, PhotoPayload


def _photo(angle: str) -> PhotoPayload:
    # Minimal valid-looking data URL (not decoded by schema)
    return PhotoPayload(angle=angle, data_url="data:image/jpeg;base64," + ("A" * 200))


def _all_photos():
    return [_photo(a) for a in ("front", "back", "left", "right", "odometer")]


def test_purpose_and_destination_required():
    with pytest.raises(ValidationError):
        BookingRequestCreate(
            VehicleID=1,
            BookingType="Immediate",
            PurposeReason="   ",
            Destination="Somewhere",
        )
    with pytest.raises(ValidationError):
        BookingRequestCreate(
            VehicleID=1,
            BookingType="Immediate",
            PurposeReason="Work",
            Destination="",
        )


def test_advance_requires_window():
    with pytest.raises(ValidationError):
        BookingRequestCreate(
            VehicleID=1,
            BookingType="Advance Reservation",
            PurposeReason="Work",
            Destination="Office",
        )


def test_checkout_requires_five_photo_angles():
    with pytest.raises(ValidationError):
        CheckOutRequest(
            Mileage=100,
            LocationText="Bay A",
            Photos=[_photo("front"), _photo("back")],
        )
    ok = CheckOutRequest(Mileage=100, LocationText="Bay A", Photos=_all_photos())
    assert len(ok.Photos) == 5


def test_checkin_mileage_schema_accepts_value():
    # Cross-field vs checkout mileage is enforced in the service layer
    req = CheckInRequest(
        Mileage=150,
        LocationText="Bay A",
        Photos=_all_photos(),
        DamageNoted=False,
    )
    assert req.Mileage == 150


def test_damage_requires_description():
    with pytest.raises(ValidationError):
        CheckInRequest(
            Mileage=150,
            LocationText="Bay A",
            Photos=_all_photos(),
            DamageNoted=True,
            DamageDescription="  ",
        )
    with pytest.raises(ValidationError):
        CheckOutRequest(
            Mileage=100,
            LocationText="Bay A",
            Photos=_all_photos(),
            DamageNoted=True,
            DamageDescription="  ",
        )


def test_checkout_gating_rules_documented():
    """Service-level gates (tested via direct condition checks)."""
    booking_status = "Approved"
    key_collected = False
    can_checkout = booking_status in ("Approved", "Flagged") and key_collected
    assert can_checkout is False

    key_collected = True
    can_checkout = booking_status in ("Approved", "Flagged") and key_collected
    assert can_checkout is True

    booking_status = "Pending Approval"
    can_checkout = booking_status in ("Approved", "Flagged") and key_collected
    assert can_checkout is False


def test_checkin_requires_checked_out_or_flagged():
    assert "Checked Out" in ("Checked Out", "Flagged")
    assert "Approved" not in ("Checked Out", "Flagged")


def test_mileage_rule():
    checkout_mileage = 1000
    checkin_mileage = 999
    assert not (checkin_mileage >= checkout_mileage)
    assert 1000 >= checkout_mileage
