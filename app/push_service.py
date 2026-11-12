"""Versand von Push-Benachrichtigungen an iOS-Geraete ueber Apple Push Notification
service (APNs), HTTP/2-API mit Token-Authentifizierung (.p8-Schluessel).

Ist APNs nicht konfiguriert, wird (wie beim E-Mail-Versand) nur eine Warnung
protokolliert; die Anwendung funktioniert dann unveraendert ohne Push.
"""

import logging
import time
from pathlib import Path

import httpx
from jose import jwt

from app.config import settings
from app.db.session import SessionLocal
from app.models.models import DeviceToken, DevicePlatform

logger = logging.getLogger("push_service")

APNS_HOST_PRODUCTION = "https://api.push.apple.com"
APNS_HOST_SANDBOX = "https://api.sandbox.push.apple.com"
# Apple verlangt, dass das Anbieter-Token hoechstens 60 Minuten alt ist, und drosselt
# Anbieter, die es oefter als alle 20 Minuten erneuern.
PROVIDER_TOKEN_LIFETIME_SECONDS = 45 * 60
# Gruende, bei denen ein Geraete-Token dauerhaft ungueltig ist und entfernt wird.
# (DeviceTokenNotForTopic / falsche Umgebung sind Konfigurationsfehler, kein Grund
# zum Loeschen.)
PERMANENT_TOKEN_ERRORS = {"BadDeviceToken", "Unregistered"}
# Eine "Ladepunkt wird frei"-Nachricht ist nach kurzer Zeit wertlos.
NOTIFICATION_TTL_SECONDS = 15 * 60

_provider_token: str | None = None
_provider_token_issued_at: float = 0.0
# Nur fuer Tests: ersetzt den HTTP-Transport (httpx.MockTransport).
_transport_override: httpx.AsyncBaseTransport | None = None


def is_configured() -> bool:
    return bool(
        settings.apns_key_id
        and settings.apns_team_id
        and settings.apns_bundle_id
        and (settings.apns_auth_key or settings.apns_auth_key_path)
    )


def _load_auth_key() -> str:
    if settings.apns_auth_key:
        # In .env-Dateien wird der mehrzeilige Schluessel mit "\n" in einer Zeile abgelegt.
        return settings.apns_auth_key.replace("\\n", "\n")
    return Path(settings.apns_auth_key_path).read_text(encoding="utf-8")


def _get_provider_token() -> str:
    global _provider_token, _provider_token_issued_at
    now = time.time()
    if _provider_token is None or now - _provider_token_issued_at > PROVIDER_TOKEN_LIFETIME_SECONDS:
        _provider_token = jwt.encode(
            {"iss": settings.apns_team_id, "iat": int(now)},
            _load_auth_key(),
            algorithm="ES256",
            headers={"kid": settings.apns_key_id},
        )
        _provider_token_issued_at = now
    return _provider_token


def _reset_provider_token() -> None:
    global _provider_token
    _provider_token = None


def _base_url() -> str:
    return APNS_HOST_SANDBOX if settings.apns_use_sandbox else APNS_HOST_PRODUCTION


def _remove_device_tokens(push_tokens: list[str]) -> None:
    if not push_tokens:
        return
    db = SessionLocal()
    try:
        db.query(DeviceToken).filter(DeviceToken.push_token.in_(push_tokens)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


async def send_push(push_tokens: list[str], title: str, body: str, data: dict | None = None) -> int:
    """Sendet eine Benachrichtigung an die angegebenen APNs-Geraete-Tokens.
    Liefert die Anzahl erfolgreich angenommener Nachrichten. Wirft nie: Push ist ein
    Zusatzkanal und darf den eigentlichen Vorgang nicht stoeren."""
    if not push_tokens:
        return 0
    if not is_configured():
        logger.warning("APNs nicht konfiguriert, Push wird nicht versendet: %s", title)
        return 0

    payload = {"aps": {"alert": {"title": title, "body": body}, "sound": "default"}}
    if data:
        payload.update(data)

    delivered = 0
    invalid_tokens: list[str] = []
    try:
        headers = {
            "authorization": f"bearer {_get_provider_token()}",
            "apns-topic": settings.apns_bundle_id,
            "apns-push-type": "alert",
            "apns-priority": "10",
            "apns-expiration": str(int(time.time()) + NOTIFICATION_TTL_SECONDS),
        }
        async with httpx.AsyncClient(
            http2=_transport_override is None, base_url=_base_url(), timeout=10, transport=_transport_override
        ) as client:
            for token in push_tokens:
                try:
                    response = await client.post(f"/3/device/{token}", json=payload, headers=headers)
                except httpx.HTTPError as exc:
                    logger.error("APNs nicht erreichbar: %s", exc)
                    break
                if response.status_code == 200:
                    delivered += 1
                    continue
                try:
                    reason = response.json().get("reason", "")
                except ValueError:
                    reason = ""
                if response.status_code == 410 or reason in PERMANENT_TOKEN_ERRORS:
                    invalid_tokens.append(token)
                elif reason in ("ExpiredProviderToken", "InvalidProviderToken"):
                    _reset_provider_token()
                    logger.error("APNs lehnt das Anbieter-Token ab (%s). Key-ID, Team-ID und Schluessel pruefen.", reason)
                    break
                else:
                    logger.error("APNs-Fehler %s (%s) fuer Geraet ...%s", response.status_code, reason, token[-6:])
    except Exception as exc:  # noqa: BLE001 - z. B. Schluesseldatei fehlt oder ist ungueltig
        logger.error("Push-Versand fehlgeschlagen: %s", exc)

    try:
        _remove_device_tokens(invalid_tokens)
    except Exception as exc:  # noqa: BLE001
        logger.error("Ungueltige Geraete-Tokens konnten nicht entfernt werden: %s", exc)
    return delivered


def ios_push_tokens_for_user(user_id: str, db) -> list[str]:
    rows = (
        db.query(DeviceToken.push_token)
        .filter(
            DeviceToken.user_id == user_id,
            DeviceToken.is_active == True,  # noqa: E712
            DeviceToken.platform == DevicePlatform.IOS,
        )
        .all()
    )
    return [token for (token,) in rows]
