"""Email notification abstraction (SMTP). No-ops gracefully when unconfigured."""

import smtplib
from email.mime.text import MIMEText

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("notify.email")


def email_configured() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.email_from)


def send_email(to: str, subject: str, body: str) -> tuple[bool, str]:
    settings = get_settings()
    if not email_configured():
        return False, "smtp not configured"
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = settings.email_from
        msg["To"] = to
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.starttls()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(settings.email_from, [to], msg.as_string())
        log.info("notification.sent", channel="email", to=to)
        return True, ""
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:300]
        log.warn("notification.failed", channel="email", error=error)
        return False, error
