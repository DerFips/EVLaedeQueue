from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
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
from app.push_service import send_push, ios_push_tokens_for_user
from app.rewards import points_for_offer

router = APIRouter(prefix="/api/v1/checkout", tags=["checkout"])


class CheckoutDecisionRequest(BaseModel):
    action: Literal["notify", "skip"]


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


def _notify_and_complete(
    session_obj: ChargingSession, entry: QueueEntry, db: Session, background_tasks: BackgroundTasks
) -> None:
    notified_email = db.query(User.email).filter(User.id == entry.user_id).scalar()
    subject, body = build_queue_notification_email(
        location_name=session_obj.charging_point.location.name,
        charging_point_label=session_obj.charging_point.label,
    )
    # Versand nach der Antwort: ein langsamer oder nicht erreichbarer SMTP-Server
    # (Timeout 10 s) haelt das Abstoepseln sonst entsprechend lange auf.
    if notified_email:
        background_tasks.add_task(send_email, notified_email, subject, body)

    # Zusaetzlich per Push an die App der wartenden Person (falls Geraete registriert).
    push_tokens = ios_push_tokens_for_user(entry.user_id, db)
    if push_tokens:
        background_tasks.add_task(
            send_push,
            push_tokens,
            "Du bist an der Reihe",
            f"{session_obj.charging_point.label} bei {session_obj.charging_point.location.name} "
            "wird frei. Bitte jetzt einchecken.",
            {
                "type": "queue_turn",
                "charging_point_id": session_obj.charging_point_id,
                "location_id": session_obj.charging_point.location_id,
            },
        )

    entry.status = QueueStatus.NOTIFIED
    entry.notified_at = datetime.now(timezone.utc)

    # Belohnungs-Anspruch (AP10) wird hier nur VORGEMERKT, nicht ausgezahlt. Die
    # tatsaechliche Gutschrift erfolgt erst beim Check-in der wartenden Person
    # (siehe app/routers/charging.py), damit Punkte nicht fuer ein Angebot vergeben
    # werden, das gar nicht genutzt wird.
    entry.benefactor_user_id = session_obj.user_id
    entry.reward_points_pending = points_for_offer(entry.parking_offer)

    _complete_session(session_obj, db)


@router.post("/charging-points/{point_id}/initiate", response_model=CheckoutInitiateResponse)
def initiate_checkout(
    point_id: str,
    background_tasks: BackgroundTasks,
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
        _notify_and_complete(session_obj, next_entry, db, background_tasks)
        return CheckoutInitiateResponse(
            action="completed",
            message="Naechste Person bietet kostenlosen Parkplatz, wurde automatisch benachrichtigt.",
            pending_entry_id=next_entry.id,
            pending_user_parking_offer=next_entry.parking_offer.value,
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
def checkout_decision(
    point_id: str,
    background_tasks: BackgroundTasks,
    payload: CheckoutDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_obj = _get_active_session_or_404(point_id, current_user, db)
    if not session_obj.checkout_pending:
        raise HTTPException(status_code=400, detail="Kein ausstehender Abstoepsel-Vorgang fuer diesen Ladepunkt")

    current_entry = _next_waiting_entry(point_id, db)
    if current_entry is None:
        _complete_session(session_obj, db)
        return CheckoutActionResponse(action="completed", message="Warteschlange ist leer, Ladevorgang abgeschlossen.")

    if payload.action == "notify":
        _notify_and_complete(session_obj, current_entry, db, background_tasks)
        return CheckoutActionResponse(
            action="completed",
            message="Wartende Person wurde benachrichtigt, Ladevorgang abgeschlossen.",
            pending_entry_id=current_entry.id,
            pending_user_parking_offer=current_entry.parking_offer.value,
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
        _notify_and_complete(session_obj, next_entry, db, background_tasks)
        return CheckoutActionResponse(
            action="completed",
            message="Person uebersprungen. Naechste Person bietet kostenlosen Parkplatz, automatisch benachrichtigt.",
            pending_entry_id=next_entry.id,
            pending_user_parking_offer=next_entry.parking_offer.value,
        )

    return CheckoutActionResponse(
        action="skipped_next_pending",
        message="Person uebersprungen. Naechste Person bietet ebenfalls keinen kostenlosen Parkplatz, bitte erneut entscheiden.",
        pending_entry_id=next_entry.id,
        pending_user_parking_offer=next_entry.parking_offer.value,
    )
