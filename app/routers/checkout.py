from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.models import (
    ChargingPoint, ChargingSession, ChargingSessionStatus,
    QueueEntry, QueueStatus, ParkingOfferType, User,
)
from app.schemas_checkout import CheckoutInitiateResponse, CheckoutActionResponse
from app.deps import get_current_user
from app.email_service import send_email, build_queue_notification_email

router = APIRouter(prefix="/api/v1/checkout", tags=["checkout"])


class CheckoutDecisionRequest(BaseModel):
    action: str


def _get_active_session_or_404(point_id: str, current_user: User, db: Session) -> ChargingSession:
    session_obj = (
        db.query(ChargingSession)
        .options(joinedload(ChargingSession.charging_point).joinedload(ChargingPoint.location))
        .filter(ChargingSession.charging_point_id == point_id, ChargingSession.status == ChargingSessionStatus.ACTIVE)
        .first()
    )
    if not session_obj:
        raise HTTPException(status_code=404, detail="Kein aktiver Ladevorgang an diesem Ladepunkt")
    if session_obj.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Nur die ladende Person kann diesen Vorgang steuern")
    return session_obj


def _next_waiting_entry(point_id: str, db: Session) -> QueueEntry | None:
    return (
        db.query(QueueEntry)
        .filter(QueueEntry.charging_point_id == point_id, QueueEntry.status == QueueStatus.WAITING)
        .order_by(QueueEntry.position.asc())
        .first()
    )


def _complete_session(session_obj: ChargingSession, db: Session) -> None:
    session_obj.status = ChargingSessionStatus.COMPLETED
    session_obj.checked_out_at = datetime.now(timezone.utc)
    session_obj.checkout_pending = False
    db.commit()


async def _notify_and_complete(session_obj: ChargingSession, entry: QueueEntry, db: Session) -> str:
    notified_user = db.query(User).filter(User.id == entry.user_id).first()
    subject, body = build_queue_notification_email(
        location_name=session_obj.charging_point.location.name,
        charging_point_label=session_obj.charging_point.label,
    )
    await send_email(notified_user.email, subject, body)

    entry.status = QueueStatus.NOTIFIED
    entry.notified_at = datetime.now(timezone.utc)
    db.commit()

    _complete_session(session_obj, db)
    return notified_user.email


@router.post("/charging-points/{point_id}/initiate", response_model=CheckoutInitiateResponse)
async def initiate_checkout(
    point_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_obj = _get_active_session_or_404(point_id, current_user, db)

    next_entry = _next_waiting_entry(point_id, db)

    if next_entry is None:
        _complete_session(session_obj, db)
        return CheckoutInitiateResponse(
            action="completed",
            message="Niemand wartet, Ladevorgang wurde abgeschlossen.",
        )

    if next_entry.parking_offer == ParkingOfferType.FREE:
        notified_email = await _notify_and_complete(session_obj, next_entry, db)
        return CheckoutInitiateResponse(
            action="completed",
            message="Naechste Person bietet kostenlosen Parkplatz, wurde automatisch benachrichtigt.",
            pending_entry_id=next_entry.id,
            pending_user_parking_offer=next_entry.parking_offer.value,
            notified_user_email=notified_email,
        )

    session_obj.checkout_pending = True
    db.commit()
    return CheckoutInitiateResponse(
        action="pending_decision",
        message="Naechste Person bietet keinen kostenlosen Parkplatz. Bitte entscheide: benachrichtigen oder ueberspringen.",
        pending_entry_id=next_entry.id,
        pending_user_parking_offer=next_entry.parking_offer.value,
    )


@router.post("/charging-points/{point_id}/decision", response_model=CheckoutActionResponse)
async def checkout_decision(
    point_id: str,
    payload: CheckoutDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.action not in ("notify", "skip"):
        raise HTTPException(status_code=400, detail="Ungueltige Aktion, erlaubt sind 'notify' oder 'skip'")

    session_obj = _get_active_session_or_404(point_id, current_user, db)
    if not session_obj.checkout_pending:
        raise HTTPException(status_code=400, detail="Kein ausstehender Abstoepsel-Vorgang fuer diesen Ladepunkt")

    current_entry = _next_waiting_entry(point_id, db)
    if current_entry is None:
        _complete_session(session_obj, db)
        return CheckoutActionResponse(action="completed", message="Warteschlange ist leer, Ladevorgang abgeschlossen.")

    if payload.action == "notify":
        notified_email = await _notify_and_complete(session_obj, current_entry, db)
        return CheckoutActionResponse(
            action="completed",
            message="Wartende Person wurde benachrichtigt, Ladevorgang abgeschlossen.",
            pending_entry_id=current_entry.id,
            pending_user_parking_offer=current_entry.parking_offer.value,
            notified_user_email=notified_email,
        )

    current_entry.status = QueueStatus.SKIPPED
    db.commit()

    next_entry = _next_waiting_entry(point_id, db)
    if next_entry is None:
        _complete_session(session_obj, db)
        return CheckoutActionResponse(
            action="skipped_and_completed",
            message="Person uebersprungen, niemand mehr in der Warteschlange, Ladevorgang abgeschlossen.",
        )

    if next_entry.parking_offer == ParkingOfferType.FREE:
        notified_email = await _notify_and_complete(session_obj, next_entry, db)
        return CheckoutActionResponse(
            action="completed",
            message="Person uebersprungen. Naechste Person bietet kostenlosen Parkplatz, automatisch benachrichtigt.",
            pending_entry_id=next_entry.id,
            pending_user_parking_offer=next_entry.parking_offer.value,
            notified_user_email=notified_email,
        )

    return CheckoutActionResponse(
        action="skipped_next_pending",
        message="Person uebersprungen. Naechste Person bietet ebenfalls keinen kostenlosen Parkplatz, bitte erneut entscheiden.",
        pending_entry_id=next_entry.id,
        pending_user_parking_offer=next_entry.parking_offer.value,
    )
