import logging

import aiosmtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger("email_service")


async def send_email(to_email: str, subject: str, body: str) -> bool:
    if not settings.smtp_host or not settings.smtp_user:
        logger.warning("SMTP nicht konfiguriert, E-Mail wird nicht versendet: %s -> %s", to_email, subject)
        return False

    message = EmailMessage()
    message["From"] = settings.smtp_from_email or settings.smtp_user
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=settings.smtp_use_tls,
            timeout=10,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("E-Mail-Versand fehlgeschlagen an %s: %s", to_email, exc)
        return False


def build_queue_notification_email(location_name: str, charging_point_label: str) -> tuple[str, str]:
    subject = f"Ladepunkt {charging_point_label} an {location_name} wird frei"
    body = (
        f"Hallo,\n\n"
        f"der Ladepunkt \"{charging_point_label}\" am Standort \"{location_name}\" wird in Kuerze frei, "
        f"da die aktuell ladende Person ihr Fahrzeug abstoepselt.\n"
        f"Bitte begib dich zeitnah zum Ladepunkt.\n\n"
        f"Viele Gruesse\nDein EVLädeQueue-Team"
    )
    return subject, body
