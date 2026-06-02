"""Panel transactional email: SMTP or log-only for dev."""
import logging
import smtplib
from email.message import EmailMessage
from typing import Optional

from panel_api.config import get_settings

log = logging.getLogger(__name__)

ROLE_LABELS = {
    "admin": "Admin",
    "worker": "Community language worker",
    "member": "Community member (read only)",
}


def _effective_email_mode() -> str:
    settings = get_settings()
    if settings.email_mode == "smtp" and settings.smtp_host:
        return "smtp"
    return "log"


def panel_link(path: str) -> str:
    settings = get_settings()
    base = (settings.panel_public_base_url or "http://localhost:5173").rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    if "/panel" in base or base.endswith("/panel"):
        return f"{base}{path}"
    return f"{base}/panel{path}"


def send_invite_email(*, to_email: str, role: str, raw_token: str) -> None:
    role_label = ROLE_LABELS.get(role, role)
    link = panel_link(f"/accept-invite?token={raw_token}")
    subject = "You're invited to the Woccon control panel"
    body = (
        f"You have been invited to the Woccon language control panel as: {role_label}.\n\n"
        f"Complete your account setup here (link expires in {get_settings().invite_expire_hours} hours):\n"
        f"{link}\n\n"
        "If you did not expect this invitation, you can ignore this email."
    )
    _send(to_email, subject, body, log_label="invite")


def send_password_reset_email(*, to_email: str, raw_token: str) -> None:
    link = panel_link(f"/reset-password?token={raw_token}")
    subject = "Reset your Woccon control panel password"
    body = (
        "We received a request to reset your password.\n\n"
        f"Reset your password here (link expires in {get_settings().password_reset_expire_hours} hours):\n"
        f"{link}\n\n"
        "If you did not request this, you can ignore this email."
    )
    _send(to_email, subject, body, log_label="password_reset")


def _send(to_email: str, subject: str, body: str, log_label: str) -> None:
    mode = _effective_email_mode()
    if mode == "log":
        log.info("[%s email] to=%s subject=%s\n%s", log_label, to_email, subject, body)
        return

    settings = get_settings()
    if not settings.smtp_from:
        raise RuntimeError("SMTP_FROM is required when EMAIL_MODE=smtp")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg.set_content(body)

    try:
        if settings.smtp_use_tls:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                if settings.smtp_user and settings.smtp_password:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
                if settings.smtp_user and settings.smtp_password:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
    except Exception as e:
        log.exception("Failed to send %s email to %s", log_label, to_email)
        raise RuntimeError(f"Failed to send email: {e}") from e


def email_configured() -> bool:
    return _effective_email_mode() == "smtp"
