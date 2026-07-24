from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.models import (
    Location, ChargingPoint, ChargingSession, ChargingSessionStatus,
    QueueEntry, QueueStatus, User,
)
from app.schemas_charging import LocationWithStatusOut, ChargingPointStatusOut, CheckInResponse, MySessionOut
from app.deps import get_current_user

router = APIRouter(prefix="/api/v1/charging", tags=["charging"])


def _build_location_status(location: Location, db: Session) -> LocationWithStatusOut:
    points_out = []
    for cp in location.charging_points:
        active_session = (
            db.query(ChargingSession)
            .filter(ChargingSession.charging_point_id == cp.id, ChargingSession.status == ChargingSessionStatus.ACTIVE)
            .first()
        )
        queue_count = (
            db.query(QueueEntry)
            .filter(QueueEntry.charging_point_id == cp.id, QueueEntry.status == QueueStatus.WAITING)
            .count()
        )
        points_out.append(ChargingPointStatusOut(
            id=cp.id,
            label=cp.label,
            connector_type=cp.connector_type,
            max_power_kw=cp.max_power_kw,
            is_active=cp.is_active,
            is_occupied=active_session is not None,
            current_session_id=active_session.id if active_session else None,
            queue_length=queue_count,
        ))
    return LocationWithStatusOut(
        id=location.id, name=location.name, address=location.address,
        description=location.description, is_active=location.is_active,
        charging_points=points_out,
    )


@router.get("/locations", response_model=list[LocationWithStatusOut])
def list_locations_with_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    locations = (
        db.query(Location)
        .options(joinedload(Location.charging_points))
        .filter(Location.is_active == True)  # noqa: E712
        .all()
    )
    return [_build_location_status(loc, db) for loc in locations]


@router.get("/locations/{location_id}", response_model=LocationWithStatusOut)
def get_location_with_status(
    location_id: str,
    current_user: User = Depends(get_current_user),
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
    return _build_location_status(location, db)


@router.post("/charging-points/{point_id}/check-in", response_model=CheckInResponse, status_code=status.HTTP_201_CREATED)
def check_in(
    point_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    point = db.query(ChargingPoint).filter(ChargingPoint.id == point_id).first()
    if not point:
        raise HTTPException(status_code=404, detail="Ladepunkt nicht gefunden")
    if not point.is_active:
        raise HTTPException(status_code=400, detail="Ladepunkt ist deaktiviert")

    existing_own_session = (
        db.query(ChargingSession)
        .filter(ChargingSession.user_id == current_user.id, ChargingSession.status == ChargingSessionStatus.ACTIVE)
        .first()
    )
    if existing_own_session:
        raise HTTPException(status_code=400, detail="Du bist bereits an einem anderen Ladepunkt eingecheckt")

    active_session = (
        db.query(ChargingSession)
        .filter(ChargingSession.charging_point_id == point_id, ChargingSession.status == ChargingSessionStatus.ACTIVE)
        .first()
    )
    if active_session:
        raise HTTPException(status_code=409, detail="Ladepunkt ist bereits belegt")

    session_obj = ChargingSession(
        charging_point_id=point_id,
        user_id=current_user.id,
        status=ChargingSessionStatus.ACTIVE,
    )
    db.add(session_obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ladepunkt wurde gerade belegt, bitte aktualisieren")
    db.refresh(session_obj)

    return CheckInResponse(
        session_id=session_obj.id,
        charging_point_id=point_id,
        checked_in_at=session_obj.checked_in_at.isoformat(),
    )


@router.get("/my-session", response_model=MySessionOut | None)
def get_my_active_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_obj = (
        db.query(ChargingSession)
        .options(joinedload(ChargingSession.charging_point).joinedload(ChargingPoint.location))
        .filter(ChargingSession.user_id == current_user.id, ChargingSession.status == ChargingSessionStatus.ACTIVE)
        .first()
    )
    if not session_obj:
        return None
    return MySessionOut(
        session_id=session_obj.id,
        charging_point_id=session_obj.charging_point.id,
        charging_point_label=session_obj.charging_point.label,
        location_id=session_obj.charging_point.location.id,
        location_name=session_obj.charging_point.location.name,
        checked_in_at=session_obj.checked_in_at.isoformat(),
    )
