import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Konstanter Dummy-Hash, gegen den bei unbekannter E-Mail trotzdem verifiziert wird
# (siehe routers/auth.py:login). Verhindert, dass sich per Antwortzeit-Messung
# unterscheiden laesst, ob ein Konto existiert (Timing-basierte User-Enumeration).
DUMMY_PASSWORD_HASH = pwd_context.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def create_access_token(subject: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {"sub": subject, "role": role, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token_value() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _password_fingerprint(hashed_password: str) -> str:
    return hashlib.sha256(hashed_password.encode("utf-8")).hexdigest()[:32]


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            raise JWTError("invalid token type")
        return payload
    except JWTError as exc:
        raise ValueError("invalid or expired token") from exc


def create_password_reset_token(user_id: str, hashed_password: str) -> str:
    """Der Token traegt einen Fingerabdruck des aktuellen Passwort-Hashes. Sobald das
    Passwort geaendert wurde, passt er nicht mehr - der Token ist damit nur einmal
    verwendbar und verfaellt auch bei einem regulaeren Passwortwechsel."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    payload = {"sub": user_id, "exp": expire, "type": "reset", "pwf": _password_fingerprint(hashed_password)}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_password_reset_token(token: str) -> tuple[str, str]:
    """Liefert (user_id, Passwort-Fingerabdruck)."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "reset":
            raise JWTError("invalid token type")
        return payload["sub"], payload["pwf"]
    except (JWTError, KeyError) as exc:
        raise ValueError("invalid or expired reset token") from exc


def reset_token_matches_password(fingerprint: str, hashed_password: str) -> bool:
    return secrets.compare_digest(fingerprint, _password_fingerprint(hashed_password))
