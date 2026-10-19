from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Callable

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import has_permission
from app.jobs.queue import enqueue_job
from app.metrics import increment_metric
from app.models.auth import User
from app.repositories.atm_repository import ATMRepository
from app.repositories.alert_repository import AlertRepository
from app.repositories.forecast_repository import ForecastRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.replenishment_repository import ReplenishmentRepository
from app.realtime import publish_realtime_event
from app.services.alert_service import AlertNotFoundError, AlertService, AlertStateError


logger = logging.getLogger(__name__)


TelegramSender = Callable[[str, str], None]
EmailSender = Callable[[str, str, str], None]
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


class NotificationConfigurationError(RuntimeError):
    pass


class TelegramTestConfigurationError(RuntimeError):
    pass


def register_telegram_webhook() -> bool:
    if not settings.telegram_token or not settings.telegram_webhook_url or not settings.telegram_webhook_secret:
        return False
    payload: dict[str, object] = {
        "url": settings.telegram_webhook_url,
        "allowed_updates": ["message"],
    }
    if settings.telegram_webhook_secret:
        payload["secret_token"] = settings.telegram_webhook_secret
    response = httpx.post(
        f"https://api.telegram.org/bot{settings.telegram_token}/setWebhook",
        json=payload,
        timeout=10.0,
    )
    response.raise_for_status()
    if not response.json().get("ok"):
        raise RuntimeError("Telegram webhook registration was rejected")
    return True


def _telegram_send(chat_id: str, text: str) -> None:
    if not settings.telegram_token:
        raise RuntimeError("Telegram provider is not configured")
    response = httpx.post(
        f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10.0,
    )
    response.raise_for_status()
    if not response.json().get("ok"):
        raise RuntimeError("Telegram provider rejected the message")


def _smtp_send(recipient: str, subject: str, body: str) -> None:
    if not settings.smtp_username or not settings.smtp_password or not settings.smtp_from_email:
        raise RuntimeError("SMTP provider is not configured")
    if settings.smtp_host != "smtp.gmail.com" or settings.smtp_port != 587:
        raise RuntimeError("SMTP must use smtp.gmail.com on port 587")
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    context = ssl.create_default_context()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)


def _gmail_api_send(recipient: str, subject: str, body: str) -> None:
    required = (
        settings.gmail_api_client_id,
        settings.gmail_api_client_secret,
        settings.gmail_api_refresh_token,
        settings.gmail_api_sender_email,
    )
    if not all(required):
        raise RuntimeError("Gmail API provider is not configured")

    try:
        token_response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.gmail_api_client_id,
                "client_secret": settings.gmail_api_client_secret,
                "refresh_token": settings.gmail_api_refresh_token,
                "grant_type": "refresh_token",
                "scope": GMAIL_SEND_SCOPE,
            },
            timeout=15.0,
        )
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise RuntimeError("Gmail API token response was invalid")

        message = EmailMessage()
        message["From"] = settings.gmail_api_sender_email
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        api_response = httpx.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")},
            timeout=15.0,
        )
        api_response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise RuntimeError("Gmail API request timed out") from exc
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise RuntimeError("Gmail API request failed") from exc


class NotificationService:
    LINK_TOKEN_TTL = timedelta(minutes=10)

    def __init__(
        self,
        session: Session,
        telegram_sender: TelegramSender | None = None,
        email_sender: EmailSender | None = None,
    ):
        self.session = session
        self.repository = NotificationRepository(session)
        self.telegram_sender = telegram_sender or _telegram_send
        self.email_sender = email_sender or self._configured_email_sender()

    @staticmethod
    def _configured_email_sender() -> EmailSender:
        if settings.notification_email_provider == "gmail_api":
            return _gmail_api_send
        return _smtp_send

    def notify(self, event_type: str, subject: str, message: str) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        telegram_users = self.repository.linked_users()
        if not telegram_users:
            results.append(self._deliver(event_type, "TELEGRAM", "", subject, message, None))
        else:
            for user in telegram_users:
                results.append(
                    self._deliver(
                        event_type,
                        "TELEGRAM",
                        user.telegram_chat_id or "",
                        subject,
                        message,
                        user.telegram_chat_id,
                    )
                )

        recipients = settings.notification_email_recipients or tuple(
            recipient
            for recipient in (settings.smtp_from_email or settings.smtp_username,)
            if recipient
        )
        if not recipients:
            results.append(self._deliver(event_type, "EMAIL", "", subject, message, None))
        else:
            for recipient in recipients:
                results.append(self._deliver(event_type, "EMAIL", recipient, subject, message, recipient))
        return results

    def send_test_email(self) -> dict[str, object]:
        recipients = tuple(dict.fromkeys(settings.notification_email_recipients))
        if not recipients:
            raise NotificationConfigurationError(
                "NOTIFICATION_EMAIL_RECIPIENTS is not configured"
            )

        subject = "[ATM Cash Intelligence] SMTP test email"
        message = (
            "This is a diagnostic test email from ATM Cash Intelligence.\n\n"
            "It confirms the configured Gmail SMTP delivery path. "
            "It is not an operational alert or replenishment request."
        )
        deliveries = [
            self._deliver("EMAIL_TEST", "EMAIL", recipient, subject, message, recipient)
            for recipient in recipients
        ]
        failed = sum(1 for delivery in deliveries if delivery["status"] != "SENT")
        return {
            "status": "FAILED" if failed else "SENT",
            "attempted": len(deliveries),
            "succeeded": len(deliveries) - failed,
            "failed": failed,
            "deliveries": deliveries,
        }

    def send_test_telegram(self, user: User) -> dict[str, object]:
        if not user.is_active:
            raise TelegramTestConfigurationError("TELEGRAM_ACCOUNT_INACTIVE")
        if not user.telegram_chat_id:
            raise TelegramTestConfigurationError("TELEGRAM_ACCOUNT_NOT_LINKED")
        return self._deliver(
            "TELEGRAM_TEST",
            "TELEGRAM",
            user.telegram_chat_id,
            "ATM Cash Intelligence Telegram test",
            "This is a Telegram delivery test for your linked account.",
            user.telegram_chat_id,
        )

    def enqueue_notification(self, event_type: str, subject: str, message: str, *, dedupe_key: str) -> dict[str, object]:
        job = enqueue_job(
            self.session,
            "notification.delivery",
            {"event_type": event_type, "subject": subject, "message": message},
            dedupe_key=dedupe_key,
        )
        return {"job_id": job.id, "status": job.status}

    def create_link_token(self, user: User) -> dict[str, object]:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + self.LINK_TOKEN_TTL
        self.repository.create_link_token(user.id, self._hash_token(token), expires_at)
        return {"token": token, "expires_at": expires_at.isoformat()}

    @staticmethod
    def telegram_status(user: User) -> dict[str, object]:
        username = settings.telegram_bot_username
        return {
            "connected": bool(user.telegram_chat_id),
            "bot_username": username,
            "bot_link": f"https://t.me/{username}" if username else None,
        }

    def handle_update(self, update: dict[str, object]) -> str | None:
        message = update.get("message")
        if not isinstance(message, dict):
            return None
        chat = message.get("chat")
        text = message.get("text")
        if not isinstance(chat, dict) or not isinstance(text, str):
            return None
        chat_id = str(chat.get("id", ""))
        if not chat_id:
            return None
        response = self.handle_command(chat_id, text.strip())
        if response:
            self._deliver("TELEGRAM_COMMAND", "TELEGRAM", chat_id, "ATM Cash Intelligence", response, chat_id)
        return response

    def handle_command(self, chat_id: str, text: str) -> str:
        command, _, argument = text.partition(" ")
        command = command.split("@", 1)[0].lower()
        argument = argument.strip()
        if command in {"/start", "/help"}:
            return (
                "ATM Cash Intelligence commands: /status, /alerts, /critical, /atm <id>, "
                "/forecast <id>, /acknowledge <alert_id>. Link your account with /link <one-time-token>."
            )
        if command == "/link":
            if not argument or not self.repository.consume_link_token(self._hash_token(argument), chat_id):
                return "Invalid or expired link token. Generate a new token from your authenticated account."
            return "Telegram account linked successfully."

        user = self.repository.get_linked_user(chat_id)
        if user is None or not user.is_active:
            return "Account not linked. Generate a one-time link token from your authenticated account, then use /link <token>."

        if command == "/approve":
            return "Replenishment approval is web-only. Use the authenticated web application."
        if command == "/status":
            if not self._allowed(user, "dashboard:read"):
                return "Permission denied."
            open_alerts = AlertRepository(self.session).count_by_status("OPEN")
            requested = ReplenishmentRepository(self.session).count_by_status("REQUESTED")
            return f"Open alerts: {open_alerts}. Replenishments awaiting review: {requested}."
        if command in {"/alerts", "/critical"}:
            if not self._allowed(user, "alerts:read"):
                return "Permission denied."
            alerts = [
                alert
                for alert in AlertService(self.session).list_alerts()
                if alert["status"] in {"OPEN", "ACKNOWLEDGED"}
            ]
            if command == "/critical":
                alerts = [alert for alert in alerts if alert["severity"] == "CRITICAL"]
            if not alerts:
                return "No matching open alerts."
            return "\n".join(
                f"#{item['alert_id']} {item['severity']} {item['atm_id']}: {item['message']}"
                for item in alerts[:20]
            )
        if command == "/atm":
            if not self._allowed(user, "dashboard:read"):
                return "Permission denied."
            if not argument:
                return "Usage: /atm <id>"
            atm = self._get_atm(argument)
            if atm is None:
                return "ATM not found."
            return (
                f"{atm.atm_code}: status {atm.status}, cash {atm.current_cash:.2f} / "
                f"capacity {atm.capacity:.2f}, daily demand {atm.daily_demand:.2f}."
            )
        if command == "/forecast":
            if not self._allowed(user, "forecasts:read"):
                return "Permission denied."
            if not argument:
                return "Usage: /forecast <id>"
            atm = self._get_atm(argument)
            if atm is None:
                return "ATM not found."
            forecasts = ForecastRepository(self.session).list_for_atm(atm.id)
            if not forecasts:
                return "No forecast available."
            forecast = forecasts[0]
            return (
                f"{atm.atm_code} forecast: risk {forecast.risk_level}, "
                f"demand {forecast.predicted_demand:.2f}, recommended top-up {forecast.recommended_top_up:.2f}."
            )
        if command == "/acknowledge":
            if not self._allowed(user, "alerts:acknowledge"):
                return "Permission denied."
            if not argument.isdecimal():
                return "Usage: /acknowledge <alert_id>"
            try:
                alert = AlertService(self.session).acknowledge(
                    int(argument), user.username, "TELEGRAM", user_id=user.id
                )
            except (AlertNotFoundError, AlertStateError):
                return "Alert not found or cannot be acknowledged in its current state."
            return f"Alert #{alert['alert_id']} acknowledged."
        return "Unknown command. Use /help."

    def _deliver(
        self,
        event_type: str,
        channel: str,
        recipient: str,
        subject: str,
        message: str,
        target: str | None,
    ) -> dict[str, object]:
        try:
            if target is None:
                raise RuntimeError("No recipient configured or linked")
            if channel == "TELEGRAM":
                self.telegram_sender(target, f"{subject}\n{message}")
            else:
                self.email_sender(target, subject, message)
        except Exception as exc:
            status = "FAILED"
            error = type(exc).__name__
            if channel == "EMAIL":
                details: dict[str, object] = {
                    "event_type": event_type,
                    "channel": channel,
                    "error_type": type(exc).__name__,
                }
                if settings.notification_email_provider == "smtp":
                    details["smtp_host"] = settings.smtp_host
                    details["smtp_port"] = settings.smtp_port
                    if isinstance(exc, smtplib.SMTPResponseException):
                        details["smtp_code"] = exc.smtp_code
                else:
                    details["provider"] = settings.notification_email_provider
                logger.warning("email_notification_delivery_failed", extra=details)
        else:
            status = "SENT"
            error = None
        increment_metric("notification_failure_total" if status == "FAILED" else "notification_success_total")
        entry = self.repository.log_delivery(event_type, channel, recipient, status, error)
        publish_realtime_event(
            "notification.delivery",
            "NOTIFICATION",
            entry.id,
            status=status,
            source="SYSTEM",
        )
        return {"delivery_id": entry.id, "channel": channel, "status": status}

    def _get_atm(self, identifier: str):
        repository = ATMRepository(self.session)
        atm = repository.get_by_code(identifier)
        if atm is None and identifier.isdecimal():
            atm = repository.get(int(identifier))
        return atm

    @staticmethod
    def _allowed(user: User, permission: str) -> bool:
        return has_permission(user.role.name, permission)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_webhook_secret(configured_secret: str | None, supplied_secret: str | None) -> bool:
    return bool(configured_secret and supplied_secret and hmac.compare_digest(configured_secret, supplied_secret))
