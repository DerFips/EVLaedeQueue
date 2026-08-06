"""Endpunkte fuer das Belohnungssystem (AP10): eigener Punktestand, Leaderboard
mit Opt-In-Sichtbarkeit (als Nutzer oder als Auto), Autoverwaltung und
Profilbild- bzw. Auto-Foto-Upload mit serverseitiger Validierung."""

import io
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import desc
from sqlalchemy.orm import Session
from PIL import Image, ImageOps, UnidentifiedImageError

from app.db.session import get_db
from app.models.models import User, Car
from app.schemas_rewards import (
    LeaderboardOptInRequest, LeaderboardDisplayRequest, LeaderboardEntryOut, MyRewardsOut,
    AvatarUploadResponse, CarCreateRequest, CarUpdateRequest, CarOut, CarPhotoUploadResponse,
)
from app.deps import get_current_user
from app.config import settings

router = APIRouter(prefix="/api/v1/rewards", tags=["rewards"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"
AVATAR_DIR = STATIC_ROOT / "avatars"
CAR_PHOTO_DIR = STATIC_ROOT / "cars"
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
CAR_PHOTO_DIR.mkdir(parents=True, exist_ok=True)


def _process_and_save_image(raw_bytes: bytes, target_dir: Path) -> str:
    """Validiert echten Bildinhalt, schneidet quadratisch zu, skaliert und speichert
    komprimiert als JPEG. Wird sowohl fuer Avatare als auch Auto-Fotos verwendet."""
    try:
        image = Image.open(io.BytesIO(raw_bytes))
        image.verify()
        image = Image.open(io.BytesIO(raw_bytes))
        image.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="Datei ist kein gueltiges Bild")

    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")

    target_size = settings.avatar_output_size_px
    short_side = min(image.size)
    left = (image.width - short_side) // 2
    top = (image.height - short_side) // 2
    image = image.crop((left, top, left + short_side, top + short_side))
    image = image.resize((target_size, target_size), Image.LANCZOS)

    filename = f"{uuid.uuid4().hex}.jpg"
    output_path = target_dir / filename
    image.save(output_path, format="JPEG", quality=85, optimize=True)
    return filename


async def _read_and_validate_upload(file: UploadFile) -> bytes:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Nur JPEG-, PNG- oder WebP-Bilder sind erlaubt")
    max_bytes = settings.avatar_max_upload_bytes
    raw_bytes = await file.read(max_bytes + 1)
    if len(raw_bytes) > max_bytes:
        raise HTTPException(status_code=413, detail="Datei ist zu gross, maximal 2 MB erlaubt")
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Leere Datei")
    return raw_bytes


def _leaderboard_display_name(user: User) -> tuple[str, str | None, bool]:
    """Liefert (Anzeigename, Bildpfad, ist_auto) je nach Praeferenz des Nutzers."""
    if user.leaderboard_display == "car":
        primary_car = next((c for c in user.cars if c.is_primary), None)
        if primary_car:
            return primary_car.name, primary_car.photo_path, True
    return (user.nickname or user.full_name), user.avatar_path, False


def _leaderboard_rank_for(user: User, db: Session) -> int | None:
    if not user.leaderboard_opt_in:
        return None
    higher_count = (
        db.query(User)
        .filter(User.leaderboard_opt_in == True, User.reward_points > user.reward_points)  # noqa: E712
        .count()
    )
    return higher_count + 1


@router.get("/me", response_model=MyRewardsOut)
def get_my_rewards(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return MyRewardsOut(
        reward_points=current_user.reward_points,
        leaderboard_opt_in=current_user.leaderboard_opt_in,
        leaderboard_display=current_user.leaderboard_display,
        leaderboard_rank=_leaderboard_rank_for(current_user, db),
    )


@router.put("/leaderboard-opt-in", response_model=MyRewardsOut)
def set_leaderboard_opt_in(
    payload: LeaderboardOptInRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.leaderboard_opt_in = payload.leaderboard_opt_in
    db.commit()
    return MyRewardsOut(
        reward_points=current_user.reward_points,
        leaderboard_opt_in=current_user.leaderboard_opt_in,
        leaderboard_display=current_user.leaderboard_display,
        leaderboard_rank=_leaderboard_rank_for(current_user, db),
    )


@router.put("/leaderboard-display", response_model=MyRewardsOut)
def set_leaderboard_display(
    payload: LeaderboardDisplayRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.leaderboard_display == "car" and not any(c.is_primary for c in current_user.cars):
        raise HTTPException(
            status_code=400,
            detail="Lege zuerst ein Auto an und markiere es als Hauptauto, bevor du es auf dem Leaderboard anzeigen lassen kannst",
        )
    current_user.leaderboard_display = payload.leaderboard_display
    db.commit()
    return MyRewardsOut(
        reward_points=current_user.reward_points,
        leaderboard_opt_in=current_user.leaderboard_opt_in,
        leaderboard_display=current_user.leaderboard_display,
        leaderboard_rank=_leaderboard_rank_for(current_user, db),
    )


@router.get("/leaderboard", response_model=list[LeaderboardEntryOut])
def get_leaderboard(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 100))
    users = (
        db.query(User)
        .filter(User.leaderboard_opt_in == True)  # noqa: E712
        .order_by(desc(User.reward_points), User.created_at.asc())
        .limit(limit)
        .all()
    )
    entries = []
    for idx, u in enumerate(users):
        display_name, photo_path, is_car = _leaderboard_display_name(u)
        entries.append(LeaderboardEntryOut(
            rank=idx + 1,
            display_name=display_name,
            reward_points=u.reward_points,
            avatar_path=photo_path,
            is_car=is_car,
        ))
    return entries


@router.post("/avatar", response_model=AvatarUploadResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raw_bytes = await _read_and_validate_upload(file)
    filename = _process_and_save_image(raw_bytes, AVATAR_DIR)

    old_avatar = current_user.avatar_path
    current_user.avatar_path = f"/static/avatars/{filename}"
    db.commit()

    if old_avatar:
        old_path = AVATAR_DIR / old_avatar.rsplit("/", 1)[-1]
        if old_path.exists() and old_path.is_file():
            old_path.unlink()

    return AvatarUploadResponse(avatar_path=current_user.avatar_path)


@router.get("/cars", response_model=list[CarOut])
def list_my_cars(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Car).filter(Car.owner_id == current_user.id).order_by(Car.created_at.asc()).all()


@router.post("/cars", response_model=CarOut, status_code=201)
def create_car(
    payload: CarCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing_count = db.query(Car).filter(Car.owner_id == current_user.id).count()
    car = Car(
        owner_id=current_user.id,
        name=payload.name,
        brand=payload.brand,
        model=payload.model,
        is_primary=(existing_count == 0),
    )
    db.add(car)
    db.commit()
    db.refresh(car)
    return car


def _get_owned_car_or_404(car_id: str, current_user: User, db: Session) -> Car:
    car = db.query(Car).filter(Car.id == car_id, Car.owner_id == current_user.id).first()
    if not car:
        raise HTTPException(status_code=404, detail="Auto nicht gefunden")
    return car


@router.put("/cars/{car_id}", response_model=CarOut)
def update_car(
    car_id: str,
    payload: CarUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    car = _get_owned_car_or_404(car_id, current_user, db)

    if payload.name is not None:
        car.name = payload.name
    if payload.brand is not None:
        car.brand = payload.brand
    if payload.model is not None:
        car.model = payload.model
    if payload.is_primary is True:
        db.query(Car).filter(Car.owner_id == current_user.id, Car.id != car.id).update({"is_primary": False})
        car.is_primary = True
    elif payload.is_primary is False:
        car.is_primary = False

    db.commit()
    db.refresh(car)
    return car


@router.delete("/cars/{car_id}", status_code=204)
def delete_car(
    car_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    car = _get_owned_car_or_404(car_id, current_user, db)
    was_primary = car.is_primary

    if car.photo_path:
        old_path = CAR_PHOTO_DIR / car.photo_path.rsplit("/", 1)[-1]
        if old_path.exists() and old_path.is_file():
            old_path.unlink()

    db.delete(car)
    db.commit()

    if was_primary:
        next_car = db.query(Car).filter(Car.owner_id == current_user.id).order_by(Car.created_at.asc()).first()
        if next_car:
            next_car.is_primary = True
        else:
            current_user.leaderboard_display = "user"
        db.commit()
    return None


@router.post("/cars/{car_id}/photo", response_model=CarPhotoUploadResponse)
async def upload_car_photo(
    car_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    car = _get_owned_car_or_404(car_id, current_user, db)
    raw_bytes = await _read_and_validate_upload(file)
    filename = _process_and_save_image(raw_bytes, CAR_PHOTO_DIR)

    old_photo = car.photo_path
    car.photo_path = f"/static/cars/{filename}"
    db.commit()

    if old_photo:
        old_path = CAR_PHOTO_DIR / old_photo.rsplit("/", 1)[-1]
        if old_path.exists() and old_path.is_file():
            old_path.unlink()

    return CarPhotoUploadResponse(photo_path=car.photo_path)
