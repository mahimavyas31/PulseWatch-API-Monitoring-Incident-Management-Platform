"""Notifications: email (SMTP) and Slack-compatible webhooks.
Failures here are logged and never break the checking loop."""
import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.config import settings
from app.services.url_validator import UnsafeURLError, validate_destination

logger = logging.getLogger(__name__)


def _send_email(monitor, subject: str, body: str) -> None:
    if not settings.smtp_host:
        logger.warning("ALERT (SMTP not configured): %s", subject)
        return
    try:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, settings.smtp_from, monitor.owner.email
        msg.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    except Exception:
        logger.exception("Failed to send alert email")


def _post_webhook(url: str, payload: dict) -> None:
    httpx.post(url, json=payload, timeout=5, follow_redirects=False).raise_for_status()


def _send_webhook(monitor, subject: str, body: str) -> None:
    try:
        validate_destination(monitor.webhook_url)  # re-check: never POST to internal addresses
        _post_webhook(monitor.webhook_url, {"text": f"*{subject}*\n{body}"})
    except UnsafeURLError:
        logger.warning("Webhook for monitor %s blocked (unsafe destination)", monitor.name)
    except Exception:
        logger.exception("Failed to send webhook")


def notify(monitor, subject: str, body: str) -> None:
    _send_email(monitor, subject, body)
    if monitor.webhook_url:
        _send_webhook(monitor, subject, body)


def alert_incident(monitor, incident, event: str) -> None:
    """event: 'opened' or 'resolved'."""
    if event == "opened":
        notify(monitor, f"[PulseWatch] {monitor.name} is DOWN",
               f"{monitor.url} failed repeated checks.\nReason: {incident.reason}")
    else:
        notify(monitor, f"[PulseWatch] {monitor.name} has RECOVERED",
               f"{monitor.url} is back up after {incident.duration_seconds} seconds.")


def alert_anomaly(monitor, result) -> None:
    notify(monitor, f"[PulseWatch] {monitor.name} is unusually slow",
           f"{monitor.url} responded in {result.response_ms} ms "
           f"(z-score {result.z_score}, well above its recent baseline).")
