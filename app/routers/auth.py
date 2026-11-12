from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import User, UserRole, RefreshToken
from app.schemas import (
    UserRegister, UserLogin, UserOut, TokenPair, RefreshRequest,
    PasswordResetRequest, PasswordResetConfirm, PasswordChange, UserProfileUpdate,
)
from app.security import (
    hash_password, verify_password, create_access_token,
    create_refresh_token_value, hash_token, create_password_reset_token,
    decode_password_reset_token, reset_token_matches_password, DUMMY_PASSWORD_HASH,
)
from app.config import settings
from app.deps import get_current_user
from app.rate_limit import limiter
from app.email_service import send_email, build_password_reset_email

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def register(request: Request, payload: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Registrierung nicht moeglich")

    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        role=UserRole.MEMBER,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _issue_token_pair(user: User, db: Session) -> TokenPair:
    # Abgelaufene Refresh-Tokens dieses Nutzers entfernen, sonst waechst die Tabelle
    # mit jeder Rotation unbegrenzt. Widerrufene, noch nicht abgelaufene bleiben fuer
    # die Replay-Erkennung erhalten.
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id, RefreshToken.expires_at < datetime.now(timezone.utc)
    ).delete(synchronize_session=False)
    access_token = create_access_token(subject=user.id, role=user.role.value)
    refresh_value = create_refresh_token_value()
    refresh_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh_value),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days),
        revoked=False,
    )
    db.add(refresh_record)
    db.commit()
    return TokenPair(access_token=access_token, refresh_token=refresh_value)


@router.post("/login", response_model=TokenPair)
@limiter.limit("10/minute")
def login(request: Request, payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    invalid_credentials = HTTPException(status_code=401, detail="Ungueltige Anmeldedaten")
    # Passwort wird auch bei unbekannter E-Mail gegen einen Dummy-Hash geprueft, damit die
    # Antwortzeit nicht verraet, ob das Konto existiert (Timing-Angriff/User-Enumeration).
    password_ok = verify_password(payload.password, user.hashed_password if user else DUMMY_PASSWORD_HASH)
    if not user or not password_ok:
        raise invalid_credentials
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Konto ist deaktiviert")
    return _issue_token_pair(user, db)


@router.post("/refresh", response_model=TokenPair)
@limiter.limit("20/minute")
def refresh_token(request: Request, payload: RefreshRequest, db: Session = Depends(get_db)):
    token_hash = hash_token(payload.refresh_token)
    record = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    invalid = HTTPException(status_code=401, detail="Ungueltiges Refresh-Token")
    if not record:
        raise invalid
    if record.revoked:
        # Wiederverwendung eines bereits rotierten/widerrufenen Refresh-Tokens deutet auf
        # Diebstahl hin (z. B. ein altes Token wurde kopiert, bevor es durch Rotation
        # widerrufen wurde). Als Vorsichtsmassnahme werden alle Refresh-Tokens dieses
        # Nutzers widerrufen, sodass ein gestohlenes Token keinen dauerhaften Zugriff mehr hat.
        db.query(RefreshToken).filter(
            RefreshToken.user_id == record.user_id, RefreshToken.revoked == False  # noqa: E712
        ).update({"revoked": True})
        db.commit()
        raise invalid
    if record.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise invalid

    user = db.query(User).filter(User.id == record.user_id).first()
    if not user or not user.is_active:
        raise invalid

    record.revoked = True
    db.commit()

    return _issue_token_pair(user, db)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshRequest, db: Session = Depends(get_db)):
    token_hash = hash_token(payload.refresh_token)
    record = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if record:
        record.revoked = True
        db.commit()
    return None


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserOut)
def update_me(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if "full_name" in payload.model_fields_set and payload.full_name is not None:
        current_user.full_name = payload.full_name
    if "nickname" in payload.model_fields_set:
        current_user.nickname = payload.nickname
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/password/change", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
def change_password(
    request: Request,
    payload: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Aktuelles Passwort ist falsch")
    current_user.hashed_password = hash_password(payload.new_password)
    db.query(RefreshToken).filter(RefreshToken.user_id == current_user.id).update({"revoked": True})
    db.commit()
    return None


@router.post("/password/reset-request", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/minute")
def request_password_reset(
    request: Request,
    payload: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user and user.is_active:
        token = create_password_reset_token(user.id, user.hashed_password)
        # Token im URL-Fragment: wird weder an den Server gesendet (Access-Logs, Proxys)
        # noch per Referer weitergegeben.
        reset_url = f"{settings.app_base_url.rstrip('/')}/reset-password#token={token}"
        subject, body = build_password_reset_email(reset_url)
        # Versand erst nach der Antwort: die Antwortzeit verraet so nicht, ob die
        # Adresse registriert ist, und ein langsamer SMTP-Server bremst niemanden aus.
        background_tasks.add_task(send_email, user.email, subject, body)
    return {"message": "Falls die E-Mail existiert, wurde ein Reset-Link versendet."}


@router.post("/password/reset-confirm", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
def confirm_password_reset(request: Request, payload: PasswordResetConfirm, db: Session = Depends(get_db)):
    invalid = HTTPException(status_code=400, detail="Ungueltiger oder abgelaufener Token")
    try:
        user_id, fingerprint = decode_password_reset_token(payload.token)
    except ValueError:
        raise invalid

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active or not reset_token_matches_password(fingerprint, user.hashed_password):
        raise invalid

    user.hashed_password = hash_password(payload.new_password)
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id).update({"revoked": True})
    db.commit()
    return None
