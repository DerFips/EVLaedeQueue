from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.db.session import get_db
from app.models.models import (
    ChargingPoint, ChargingSession, ChargingSessionStatus,
    QueueEntry, QueueStatus, User,
)
from app.schemas_queue import QueueJoinRequest, QueueEntryOut, MyQueueStatusOut
from app.deps import get_current_user

router = APIRouter(prefix="/api/v1/queue", tags=["queue"])


@router.post("/charging-points/{point_id}/join", response_model=QueueEntryOut, status_code=status.HTTP_201_CREATED)
def join_queue(
    point_id: str,
    payload: QueueJoinRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    point = db.query(ChargingPoint).filter(ChargingPoint.id == point_id).first()
    if not point:
        raise HTTPException(status_code=404, detail="Ladepunkt nicht gefunden")
    if not point.is_active:
        raise HTTPException(status_code=400, detail="Ladepunkt ist deaktiviert")

    active_session = (
        db.query(ChargingSession)
        .filter(ChargingSession.charging_point_id == point_id, ChargingSession.status == ChargingSessionStatus.ACTIVE)
        .first()
    )
    if not active_session:
        raise HTTPException(status_code=400, detail="Ladepunkt ist frei, bitte direkt einchecken statt in Warteschlange einzutreten")

    if active_session.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Du laedst bereits selbst an diesem Ladepunkt")

    existing_entry = (
        db.query(QueueEntry)
        .filter(
            QueueEntry.charging_point_id == point_id,
            QueueEntry.user_id == current_user.id,
            QueueEntry.status.in_([QueueStatus.WAITING, QueueStatus.NOTIFIED]),
        )
        .first()
    )
    if existing_entry:
        raise HTTPException(status_code=400, detail="Du befindest dich bereits in der Warteschlange fuer diesen Ladepunkt")

    max_position = (
        db.query(func.max(QueueEntry.position))
        .filter(QueueEntry.charging_point_id == point_id, QueueEntry.status.in_([QueueStatus.WAITING, QueueStatus.NOTIFIED]))
        .scalar()
    )
    next_position = (max_position or 0) + 1

    entry = QueueEntry(
        charging_point_id=point_id,
        user_id=current_user.id,
        parking_offer=payload.parking_offer,
        status=QueueStatus.WAITING,
        position=next_position,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return QueueEntryOut(
        id=entry.id, charging_point_id=entry.charging_point_id, user_id=entry.user_id,
        parking_offer=entry.parking_offer.value, status=entry.status.value,
        position=entry.position, created_at=entry.created_at.isoformat(),
    )


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def leave_queue(
    entry_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = db.query(QueueEntry).filter(QueueEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Warteschlangeneintrag nicht gefunden")
    if entry.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf diesen Eintrag")
    if entry.status not in (QueueStatus.WAITING, QueueStatus.NOTIFIED):
        raise HTTPException(status_code=400, detail="Eintrag kann nicht mehr storniert werden")

    entry.status = QueueStatus.CANCELLED
    db.commit()
    return None


@router.get("/charging-points/{point_id}", response_model=list[QueueEntryOut])
def list_queue_for_point(
    point_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    point = db.query(ChargingPoint).filter(ChargingPoint.id == point_id).first()
    if not point:
        raise HTTPException(status_code=404, detail="Ladepunkt nicht gefunden")

    entries = (
        db.query(QueueEntry)
        .filter(QueueEntry.charging_point_id == point_id, QueueEntry.status.in_([QueueStatus.WAITING, QueueStatus.NOTIFIED]))
        .order_by(QueueEntry.position.asc())
        .all()
    )
    return [
        QueueEntryOut(
            id=e.id, charging_point_id=e.charging_point_id, user_id=e.user_id,
            parking_offer=e.parking_offer.value, status=e.status.value,
            position=e.position, created_at=e.created_at.isoformat(),
        )
        for e in entries
    ]


@router.get("/my-status", response_model=MyQueueStatusOut | None)
def get_my_queue_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = (
        db.query(QueueEntry)
        .options(joinedload(QueueEntry.charging_point).joinedload(ChargingPoint.location))
        .filter(QueueEntry.user_id == current_user.id, QueueEntry.status.in_([QueueStatus.WAITING, QueueStatus.NOTIFIED]))
        .order_by(QueueEntry.created_at.desc())
        .first()
    )
    if not entry:
        return None

    people_ahead = (
        db.query(QueueEntry)
        .filter(
            QueueEntry.charging_point_id == entry.charging_point_id,
            QueueEntry.status.in_([QueueStatus.WAITING, QueueStatus.NOTIFIED]),
            QueueEntry.position < entry.position,
        )
        .count()
    )

    return MyQueueStatusOut(
        queue_entry_id=entry.id,
        charging_point_id=entry.charging_point.id,
        charging_point_label=entry.charging_point.label,
        location_id=entry.charging_point.location_id,
        location_name=entry.charging_point.location.name,
        position=entry.position,
        people_ahead=people_ahead,
        parking_offer=entry.parking_offer.value,
        status=entry.status.value,
    )
