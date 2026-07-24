from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.models import (
    DeviceToken, DevicePlatform, User,
    Location, ChargingPoint, ChargingSession, ChargingSessionStatus,
    QueueEntry, QueueStatus,
)
from app.schemas_mobile import DeviceTokenRegister, DeviceTokenOut, MobileDashboardOut
from app.deps import get_current_user

router = APIRouter(prefix="/api/v1/mobile", tags=["mobile"])


@router.post("/devices", response_model=DeviceTokenOut, status_code=status.HTTP_201_CREATED)
def register_device_token(
    payload: DeviceTokenRegister,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(DeviceToken)
        .filter(DeviceToken.user_id == current_user.id, DeviceToken.push_token == payload.push_token)
        .first()
    )
    if existing:
        existing.is_active = True
        existing.platform = DevicePlatform(payload.platform)
        db.commit()
        db.refresh(existing)
        return existing

    device = DeviceToken(
        user_id=current_user.id,
        platform=DevicePlatform(payload.platform),
        push_token=payload.push_token,
        is_active=True,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def deregister_device_token(
    device_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = db.query(DeviceToken).filter(DeviceToken.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Geraet nicht gefunden")
    if device.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf dieses Geraet")
    db.delete(device)
    db.commit()
    return None


@router.get("/dashboard", response_model=MobileDashboardOut)
def get_mobile_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    active_session = None
    session_obj = (
        db.query(ChargingSession)
        .options(joinedload(ChargingSession.charging_point).joinedload(ChargingPoint.location))
        .filter(ChargingSession.user_id == current_user.id, ChargingSession.status == ChargingSessionStatus.ACTIVE)
        .first()
    )
    if session_obj:
        active_session = {
            "session_id": session_obj.id,
            "charging_point_id": session_obj.charging_point.id,
            "charging_point_label": session_obj.charging_point.label,
            "location_name": session_obj.charging_point.location.name,
            "checked_in_at": session_obj.checked_in_at.isoformat(),
            "checkout_pending": session_obj.checkout_pending,
        }

    queue_status = None
    entry = (
        db.query(QueueEntry)
        .options(joinedload(QueueEntry.charging_point).joinedload(ChargingPoint.location))
        .filter(QueueEntry.user_id == current_user.id, QueueEntry.status.in_([QueueStatus.WAITING, QueueStatus.NOTIFIED]))
        .order_by(QueueEntry.created_at.desc())
        .first()
    )
    if entry:
        people_ahead = (
            db.query(QueueEntry)
            .filter(
                QueueEntry.charging_point_id == entry.charging_point_id,
                QueueEntry.status.in_([QueueStatus.WAITING, QueueStatus.NOTIFIED]),
                QueueEntry.position < entry.position,
            )
            .count()
        )
        queue_status = {
            "queue_entry_id": entry.id,
            "charging_point_label": entry.charging_point.label,
            "location_name": entry.charging_point.location.name,
            "position": entry.position,
            "people_ahead": people_ahead,
            "parking_offer": entry.parking_offer.value,
            "status": entry.status.value,
        }

    locations = (
        db.query(Location)
        .options(joinedload(Location.charging_points))
        .filter(Location.is_active == True)  # noqa: E712
        .all()
    )
    locations_summary = []
    for loc in locations:
        total_points = len(loc.charging_points)
        occupied = 0
        for cp in loc.charging_points:
            has_active = (
                db.query(ChargingSession)
                .filter(ChargingSession.charging_point_id == cp.id, ChargingSession.status == ChargingSessionStatus.ACTIVE)
                .first()
            )
            if has_active:
                occupied += 1
        locations_summary.append({
            "location_id": loc.id,
            "name": loc.name,
            "total_points": total_points,
            "free_points": total_points - occupied,
        })

    return MobileDashboardOut(
        active_session=active_session,
        queue_status=queue_status,
        locations_summary=locations_summary,
    )
