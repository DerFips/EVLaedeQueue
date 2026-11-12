from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.session import get_db
from app.models.models import (
    Location, ChargingPoint, ChargingSession, ChargingSessionStatus,
    QueueEntry, QueueStatus, User, PointTransaction, PointTransactionReason,
)
from app.schemas_charging import LocationWithStatusOut, ChargingPointStatusOut, CheckInResponse, MySessionOut
from app.deps import get_current_user

router = APIRouter(prefix="/api/v1/charging", tags=["charging"])


def point_occupancy(point_ids: list[str], db: Session) -> tuple[dict[str, str], dict[str, int]]:
    """Liefert fuer alle angegebenen Ladepunkte in zwei Abfragen (statt zwei pro
    Ladepunkt) die aktive Session-ID und die Laenge der Warteschlange."""
    if not point_ids:
        return {}, {}
    active = dict(
        db.query(ChargingSession.charging_point_id, ChargingSession.id)
        .filter(
            ChargingSession.charging_point_id.in_(point_ids),
            ChargingSession.status == ChargingSessionStatus.ACTIVE,
        )
        .all()
    )
    queue_counts = dict(
        db.query(QueueEntry.charging_point_id, func.count(QueueEntry.id))
        .filter(QueueEntry.charging_point_id.in_(point_ids), QueueEntry.status == QueueStatus.WAITING)
        .group_by(QueueEntry.charging_point_id)
        .all()
    )
    return active, queue_counts


def _build_locations_status(locations: list[Location], db: Session) -> list[LocationWithStatusOut]:
    point_ids = [cp.id for loc in locations for cp in loc.charging_points]
    active, queue_counts = point_occupancy(point_ids, db)
    return [
        LocationWithStatusOut(
            id=loc.id, name=loc.name, address=loc.address,
            description=loc.description, is_active=loc.is_active,
            charging_points=[
                ChargingPointStatusOut(
                    id=cp.id,
                    label=cp.label,
                    connector_type=cp.connector_type,
                    max_power_kw=cp.max_power_kw,
                    is_active=cp.is_active,
                    is_occupied=cp.id in active,
                    current_session_id=active.get(cp.id),
                    queue_length=queue_counts.get(cp.id, 0),
                )
                for cp in loc.charging_points
            ],
        )
        for loc in locations
    ]


@router.get("/locations", response_model=list[LocationWithStatusOut])
def list_locations_with_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    locations = (
        db.query(Location)
        .options(selectinload(Location.charging_points))
        .filter(Location.is_active == True)  # noqa: E712
        .order_by(Location.name)
        .all()
    )
    return _build_locations_status(locations, db)


@router.get("/locations/{location_id}", response_model=LocationWithStatusOut)
def get_location_with_status(
    location_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    location = (
        db.query(Location)
        .options(selectinload(Location.charging_points))
        .filter(Location.id == location_id)
        .first()
    )
    if not location:
        raise HTTPException(status_code=404, detail="Standort nicht gefunden")
    return _build_locations_status([location], db)[0]


@router.post("/charging-points/{point_id}/check-in", response_model=CheckInResponse, status_code=status.HTTP_201_CREATED)
def check_in(
    point_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    point = (
        db.query(ChargingPoint)
        .options(joinedload(ChargingPoint.location))
        .filter(ChargingPoint.id == point_id)
        .first()
    )
    if not point:
        raise HTTPException(status_code=404, detail="Ladepunkt nicht gefunden")
    if not point.is_active or not point.location.is_active:
        raise HTTPException(status_code=400, detail="Ladepunkt ist deaktiviert")

    existing_own_session = (
        db.query(ChargingSession)
        .filter(ChargingSession.user_id == current_user.id, ChargingSession.status == ChargingSessionStatus.ACTIVE)
        .first()
    )
    if existing_own_session:
        raise HTTPException(status_code=400, detail="Du bist bereits an einem Ladepunkt eingecheckt")

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
    _settle_queue_on_check_in(point_id, current_user, db)
    try:
        # Session, Warteschlangen-Abschluss und Punktegutschrift in EINER Transaktion:
        # die Unique-Indizes fangen gleichzeitige Check-ins ab, ohne halbe Zustaende.
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


def _settle_queue_on_check_in(point_id: str, checked_in_user: User, db: Session) -> None:
    """Raeumt die Warteschlange des Ladepunkts beim Check-in auf (ohne Commit).

    - Eigene offene Eintraege werden abgeschlossen. Sonst bliebe man waehrend des
      Ladens in der eigenen Warteschlange stehen und koennte sich beim Abstoepseln
      selbst benachrichtigen und so Punkte zuschieben.
    - War man benachrichtigt, erhaelt die Person, die den Platz freigemacht hat, die
      vorgemerkten Belohnungspunkte (AP10) - nie man selbst.
    - Wurde jemand anderes benachrichtigt, hat den Platz aber nicht genutzt, rueckt
      diese Person wieder als Wartende ein; der alte Punkte-Anspruch verfaellt.
    """
    open_entries = (
        db.query(QueueEntry)
        .filter(
            QueueEntry.charging_point_id == point_id,
            or_(
                QueueEntry.status == QueueStatus.NOTIFIED,
                and_(QueueEntry.user_id == checked_in_user.id, QueueEntry.status == QueueStatus.WAITING),
            ),
        )
        .all()
    )
    for entry in open_entries:
        if entry.user_id != checked_in_user.id:
            entry.status = QueueStatus.WAITING
            entry.notified_at = None
            entry.benefactor_user_id = None
            entry.reward_points_pending = None
            continue

        if entry.status == QueueStatus.NOTIFIED:
            _award_reward(entry, checked_in_user, db)
        entry.status = QueueStatus.COMPLETED


def _award_reward(entry: QueueEntry, checked_in_user: User, db: Session) -> None:
    if (
        entry.reward_points_awarded
        or not entry.reward_points_pending
        or not entry.benefactor_user_id
        or entry.benefactor_user_id == checked_in_user.id
    ):
        return
    if db.query(PointTransaction.id).filter(PointTransaction.queue_entry_id == entry.id).first():
        return
    benefactor = db.query(User).filter(User.id == entry.benefactor_user_id).first()
    if not benefactor:
        return

    db.add(PointTransaction(
        user_id=benefactor.id,
        points=entry.reward_points_pending,
        reason=PointTransactionReason.PARKING_OFFER_HONORED,
        queue_entry_id=entry.id,
    ))
    # Atomar in SQL erhoehen statt lesen-und-schreiben, damit parallele Gutschriften
    # sich nicht gegenseitig ueberschreiben.
    benefactor.reward_points = User.reward_points + entry.reward_points_pending
    entry.reward_points_awarded = True


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
