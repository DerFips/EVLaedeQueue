import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum, Integer, Text, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def gen_uuid() -> str:
    return str(uuid.uuid4())


class UserRole(str, enum.Enum):
    MEMBER = "member"
    ADMIN = "admin"


class ParkingOfferType(str, enum.Enum):
    NONE = "none"
    FREE = "free"
    PAID = "paid"


class QueueStatus(str, enum.Enum):
    WAITING = "waiting"
    NOTIFIED = "notified"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class ChargingSessionStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, values_callable=lambda x: [e.value for e in x]), default=UserRole.MEMBER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Belohnungssystem (AP10): Punktestand, Sichtbarkeit auf dem Leaderboard (Opt-In,
    # standardmaessig deaktiviert) sowie optionales Profilbild.
    reward_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    leaderboard_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    avatar_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Spitzname: optional, wird auf dem Leaderboard und im Profil bevorzugt anstelle
    # des echten Namens angezeigt, wenn gesetzt. full_name bleibt der rechtsverbindliche
    # Name (z. B. fuer Abrechnung/Support) und ist ueber PUT /auth/me aenderbar.
    nickname: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Legt fest, was auf dem Leaderboard als Identitaet erscheint, falls der Nutzer per
    # leaderboard_opt_in sichtbar ist: der eigene (Spitz-)Name oder sein registriertes Auto.
    leaderboard_display = mapped_column(
        Enum("user", "car", name="leaderboarddisplay", values_callable=lambda x: list(x)),
        default="user",
        nullable=False,
    )

    sessions: Mapped[list["ChargingSession"]] = relationship(back_populates="user")
    queue_entries: Mapped[list["QueueEntry"]] = relationship(back_populates="user", foreign_keys="[QueueEntry.user_id]")
    point_transactions: Mapped[list["PointTransaction"]] = relationship(back_populates="user")
    cars: Mapped[list["Car"]] = relationship(back_populates="owner", cascade="all, delete-orphan")



class Car(Base):
    """Ein vom Nutzer angelegtes Fahrzeug (AP10-Erweiterung). Ein Nutzer kann mehrere
    Autos anlegen, aber nur eines davon als aktives Leaderboard-Auto markieren
    (is_primary), das dann anstelle des Nutzernamens angezeigt wird."""
    __tablename__ = "cars"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    photo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    owner: Mapped["User"] = relationship(back_populates="cars")


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    charging_points: Mapped[list["ChargingPoint"]] = relationship(back_populates="location", cascade="all, delete-orphan")


class ChargingPoint(Base):
    __tablename__ = "charging_points"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    location_id: Mapped[str] = mapped_column(String(36), ForeignKey("locations.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    connector_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    max_power_kw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    location: Mapped["Location"] = relationship(back_populates="charging_points")
    sessions: Mapped[list["ChargingSession"]] = relationship(back_populates="charging_point")
    queue_entries: Mapped[list["QueueEntry"]] = relationship(back_populates="charging_point")


class ChargingSession(Base):
    """Repraesentiert einen aktiven oder abgeschlossenen Ladevorgang (Check-in bis Abstoepseln)."""
    __tablename__ = "charging_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    charging_point_id: Mapped[str] = mapped_column(String(36), ForeignKey("charging_points.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    status: Mapped[ChargingSessionStatus] = mapped_column(Enum(ChargingSessionStatus, values_callable=lambda x: [e.value for e in x]), default=ChargingSessionStatus.ACTIVE, nullable=False)
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checkout_pending: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    charging_point: Mapped["ChargingPoint"] = relationship(back_populates="sessions")
    user: Mapped["User"] = relationship(back_populates="sessions")


Index(
    "ux_one_active_session_per_point",
    ChargingSession.charging_point_id,
    unique=True,
    sqlite_where=ChargingSession.status == ChargingSessionStatus.ACTIVE,
)


class QueueEntry(Base):
    """Ein Eintrag in der Warteschlange fuer einen Ladepunkt."""
    __tablename__ = "queue_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    charging_point_id: Mapped[str] = mapped_column(String(36), ForeignKey("charging_points.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    parking_offer: Mapped[ParkingOfferType] = mapped_column(Enum(ParkingOfferType, values_callable=lambda x: [e.value for e in x]), default=ParkingOfferType.NONE, nullable=False)
    status: Mapped[QueueStatus] = mapped_column(Enum(QueueStatus, values_callable=lambda x: [e.value for e in x]), default=QueueStatus.WAITING, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Belohnungssystem (AP10): Wer hat durch sein Abstoepseln diesen Platz freigemacht
    # (= Empfaenger der Punkte), und wie viele Punkte sind faellig. Die Gutschrift erfolgt
    # bewusst erst beim tatsaechlichen Check-in dieser wartenden Person (nicht bereits bei
    # der Benachrichtigung), damit niemand Punkte fuer ein ungenutztes Angebot bekommt.
    benefactor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    reward_points_pending: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reward_points_awarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    charging_point: Mapped["ChargingPoint"] = relationship(back_populates="queue_entries")
    user: Mapped["User"] = relationship(back_populates="queue_entries", foreign_keys=[user_id])
    benefactor: Mapped["User | None"] = relationship(foreign_keys=[benefactor_user_id])


class DevicePlatform(str, enum.Enum):
    IOS = "ios"
    ANDROID = "android"


class DeviceToken(Base):
    """Push-Notification-Token fuer mobile Geraete (APNs/FCM), um Nutzer ausserhalb der App per Push zu informieren."""
    __tablename__ = "device_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    platform: Mapped[DevicePlatform] = mapped_column(Enum(DevicePlatform, values_callable=lambda x: [e.value for e in x]), nullable=False)
    push_token: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "push_token", name="uq_user_push_token"),)


class RefreshToken(Base):
    """Persistierte Refresh-Tokens zum sicheren Widerruf (Logout / Token-Rotation)."""
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class PointTransactionReason(str, enum.Enum):
    PARKING_OFFER_HONORED = "parking_offer_honored"


class PointTransaction(Base):
    """Protokolliert jede Punktegutschrift des Belohnungssystems (AP10), um Missbrauch
    nachvollziehbar zu machen. Die Unique-Constraint auf queue_entry_id stellt sicher,
    dass fuer denselben Warteschlangeneintrag niemals doppelt Punkte vergeben werden
    (z. B. bei mehrfachem Aufruf des Check-in-Endpunkts)."""
    __tablename__ = "point_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[PointTransactionReason] = mapped_column(
        Enum(PointTransactionReason, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    queue_entry_id: Mapped[str] = mapped_column(String(36), ForeignKey("queue_entries.id"), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="point_transactions")
