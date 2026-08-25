from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Vehicle
from app.schemas.schemas import VehicleCreate, VehicleOut
from app.services.audit import write_audit
from app.services.auth import AuthUser, get_current_user, require_manager
from app.services.vehicles import (
    current_holder,
    employee_visible_vehicles,
    is_service_due_soon,
    km_until_service,
    sync_vehicle_status,
)

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


def _to_out(db: Session, v: Vehicle) -> VehicleOut:
    holder = current_holder(db, v.VehicleID)
    driver_name = None
    booking_id = None
    if holder:
        booking_id = holder.BookingID
        if holder.driver:
            driver_name = holder.driver.DisplayName
    return VehicleOut(
        VehicleID=v.VehicleID,
        RegistrationNumber=v.RegistrationNumber,
        MakeModel=v.MakeModel,
        CurrentStatus=v.CurrentStatus,
        CurrentMileage=v.CurrentMileage,
        CurrentParkingLocation=v.CurrentParkingLocation,
        ServiceIntervalKm=v.ServiceIntervalKm,
        LastServiceMileage=v.LastServiceMileage,
        ServiceAlertThresholdKm=v.ServiceAlertThresholdKm,
        LastServiceDate=v.LastServiceDate,
        NextServiceDueDate=v.NextServiceDueDate,
        IsActive=v.IsActive,
        ServiceDueSoon=is_service_due_soon(v),
        KmUntilService=km_until_service(v),
        CurrentDriverName=driver_name,
        CurrentBookingID=booking_id,
    )


@router.get("", response_model=list[VehicleOut])
def list_vehicles(
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
    all: bool = False,
):
    if all:
        if not user.is_manager_portal:
            raise HTTPException(status_code=403, detail="Manager or Admin role required")
        vehicles = db.query(Vehicle).order_by(Vehicle.RegistrationNumber).all()
    else:
        vehicles = employee_visible_vehicles(db)
    for v in vehicles:
        sync_vehicle_status(db, v)
    db.commit()
    return [_to_out(db, v) for v in vehicles]


@router.get("/service-due", response_model=list[VehicleOut])
def service_due(
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_manager),
):
    vehicles = db.query(Vehicle).filter(Vehicle.IsActive.is_(True)).all()
    return [_to_out(db, v) for v in vehicles if is_service_due_soon(v)]


@router.post("", response_model=VehicleOut)
def add_vehicle(
    payload: VehicleCreate,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(require_manager),
):
    existing = (
        db.query(Vehicle)
        .filter(Vehicle.RegistrationNumber == payload.RegistrationNumber.strip().upper())
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Registration number already exists")

    vehicle = Vehicle(
        RegistrationNumber=payload.RegistrationNumber.strip().upper(),
        MakeModel=payload.MakeModel.strip(),
        CurrentStatus="Available",
        CurrentMileage=payload.CurrentMileage,
        CurrentParkingLocation=payload.CurrentParkingLocation.strip(),
        ServiceIntervalKm=payload.ServiceIntervalKm,
        LastServiceMileage=payload.LastServiceMileage,
        ServiceAlertThresholdKm=payload.ServiceAlertThresholdKm,
        LastServiceDate=payload.LastServiceDate,
        NextServiceDueDate=payload.NextServiceDueDate,
        IsActive=True,
    )
    db.add(vehicle)
    db.flush()
    write_audit(
        db,
        table_name="Vehicles",
        record_id=vehicle.VehicleID,
        action="CREATE",
        changed_by=user.UserID,
        new_value={
            "RegistrationNumber": vehicle.RegistrationNumber,
            "MakeModel": vehicle.MakeModel,
        },
    )
    db.commit()
    db.refresh(vehicle)
    return _to_out(db, vehicle)


@router.post("/{vehicle_id}/toggle-active", response_model=VehicleOut)
def toggle_active(
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(require_manager),
):
    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    if vehicle.IsActive and vehicle.CurrentStatus != "Available":
        raise HTTPException(
            status_code=400,
            detail="Cannot deactivate a vehicle that is Reserved or In Use",
        )
    old = vehicle.IsActive
    vehicle.IsActive = not vehicle.IsActive
    write_audit(
        db,
        table_name="Vehicles",
        record_id=vehicle.VehicleID,
        action="TOGGLE_ACTIVE",
        changed_by=user.UserID,
        old_value={"IsActive": old},
        new_value={"IsActive": vehicle.IsActive},
    )
    db.commit()
    db.refresh(vehicle)
    return _to_out(db, vehicle)
