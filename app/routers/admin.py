from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.models import Location, ChargingPoint, User, QueueEntry, ChargingSession, QueueStatus
from app.schemas_admin import (
    LocationCreate, LocationUpdate, LocationOut, LocationDetailOut,
    ChargingPointCreate, ChargingPointUpdate, ChargingPointOut,
)
from app.deps import get_current_admin

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/locations", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def create_location(
    payload: LocationCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    location = Location(
        name=payload.name,
        address=payload.address,
        description=payload.description,
        created_by=admin.id,
        is_active=True,
    )
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


@router.get("/locations", response_model=list[LocationOut])
def list_locations(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return db.query(Location).order_by(Location.created_at.desc()).all()


@router.get("/locations/{location_id}", response_model=LocationDetailOut)
def get_location(
    location_id: str,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    location = (
        db.query(Location)
        .options(joinedload(Location.charging_points))
        .filter(Location.id == location_id)
        .first()
    )
    if not location:
        raise HTTPException(status_code=404, detail="Standort nicht gefunden")
    return location


@router.patch("/locations/{location_id}", response_model=LocationOut)
def update_location(
    location_id: str,
    payload: LocationUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Standort nicht gefunden")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(location, field, value)

    db.commit()
    db.refresh(location)
    return location


@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(
    location_id: str,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Standort nicht gefunden")

    active_sessions = (
        db.query(ChargingSession)
        .join(ChargingPoint, ChargingSession.charging_point_id == ChargingPoint.id)
        .filter(ChargingPoint.location_id == location_id, ChargingSession.status == "active")
        .count()
    )
    active_queue = (
        db.query(QueueEntry)
        .join(ChargingPoint, QueueEntry.charging_point_id == ChargingPoint.id)
        .filter(ChargingPoint.location_id == location_id, QueueEntry.status == QueueStatus.WAITING)
        .count()
    )
    if active_sessions > 0 or active_queue > 0:
        raise HTTPException(
            status_code=400,
            detail="Standort kann nicht geloescht werden: aktive Ladevorgaenge oder Warteschlangen vorhanden",
        )

    db.delete(location)
    db.commit()
    return None


@router.post("/locations/{location_id}/charging-points", response_model=ChargingPointOut, status_code=status.HTTP_201_CREATED)
def create_charging_point(
    location_id: str,
    payload: ChargingPointCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Standort nicht gefunden")

    duplicate = (
        db.query(ChargingPoint)
        .filter(ChargingPoint.location_id == location_id, ChargingPoint.label == payload.label)
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=400, detail="Ladepunkt-Label existiert an diesem Standort bereits")

    charging_point = ChargingPoint(
        location_id=location_id,
        label=payload.label,
        connector_type=payload.connector_type,
        max_power_kw=payload.max_power_kw,
        is_active=True,
    )
    db.add(charging_point)
    db.commit()
    db.refresh(charging_point)
    return charging_point


@router.get("/locations/{location_id}/charging-points", response_model=list[ChargingPointOut])
def list_charging_points(
    location_id: str,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Standort nicht gefunden")
    return db.query(ChargingPoint).filter(ChargingPoint.location_id == location_id).all()


@router.patch("/charging-points/{point_id}", response_model=ChargingPointOut)
def update_charging_point(
    point_id: str,
    payload: ChargingPointUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    point = db.query(ChargingPoint).filter(ChargingPoint.id == point_id).first()
    if not point:
        raise HTTPException(status_code=404, detail="Ladepunkt nicht gefunden")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(point, field, value)

    db.commit()
    db.refresh(point)
    return point


@router.delete("/charging-points/{point_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_charging_point(
    point_id: str,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    point = db.query(ChargingPoint).filter(ChargingPoint.id == point_id).first()
    if not point:
        raise HTTPException(status_code=404, detail="Ladepunkt nicht gefunden")

    active_session = (
        db.query(ChargingSession)
        .filter(ChargingSession.charging_point_id == point_id, ChargingSession.status == "active")
        .first()
    )
    active_queue = (
        db.query(QueueEntry)
        .filter(QueueEntry.charging_point_id == point_id, QueueEntry.status == QueueStatus.WAITING)
        .first()
    )
    if active_session or active_queue:
        raise HTTPException(
            status_code=400,
            detail="Ladepunkt kann nicht geloescht werden: aktiver Ladevorgang oder Warteschlange vorhanden",
        )

    db.delete(point)
    db.commit()
    return None
