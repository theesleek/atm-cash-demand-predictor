from __future__ import annotations

import base64
from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import smtplib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.permissions import ROLE_DESCRIPTIONS
from app.core import config as config_module
from app.db.base import Base
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.atm import ATM, Alert, Forecast
from app.models.auth import Role, User
from app.models.notification import NotificationDelivery
from app.models.operations import BackgroundJob, NotificationOutbox
from app.models.replenishment import Replenishment
from app.jobs import queue as queue_module
from app.jobs import worker as worker_module
from app.repositories.notification_repository import NotificationRepository
from app.services import notification_service as notification_module
from app.api.routes import notifications as notification_routes
from app.services.alert_service import AlertService
from app.services.notification_service import (
    NotificationService,
    TelegramTestConfigurationError,
    verify_webhook_secret,
)
from app.services.replenishment_service import ReplenishmentService
from app.services import replenishment_service as replenishment_module


REAL_NOTIFY = NotificationService.notify


@pytest.fixture
def notification_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    roles = {name: Role(name=name, description=description) for name, description in ROLE_DESCRIPTIONS.items()}
    session.add_all(roles.values())
    session.commit()
    manager = User(username="notice-manager", password_hash="not-used", role_id=roles["BANK_MANAGER"].id)
    admin = User(username="notice-admin", password_hash="not-used", role_id=roles["SUPER_ADMIN"].id)
    atm = ATM(
        atm_code="ATM-NOTICE",
        branch_id="BRANCH-NOTICE",
        region="TEST",
        capacity=10000.0,
        current_cash=5000.0,
        daily_demand=1000.0,
    )
    session.add_all([manager, admin, atm])
    session.commit()
    session.refresh(manager)
    session.refresh(admin)
    session.refresh(atm)
    forecast = Forecast(
        atm_id=atm.id,
        forecast_date=datetime.now(timezone.utc),
        predicted_demand=1200.0,
        risk_level="HIGH",
        recommended_top_up=1200.0,
        model_version="test",
    )
    session.add(forecast)
    session.commit()
    session.refresh(forecast)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _test_settings(monkeypatch: pytest.MonkeyPatch, recipients: tuple[str, ...] = ("ops@example.test",)) -> None:
    monkeypatch.setattr(
        notification_module,
        "settings",
        replace(notification_module.settings, notification_email_recipients=recipients),
    )


def test_provider_delivery_is_mocked_and_status_is_logged(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _test_settings(monkeypatch)
    telegram_calls: list[tuple[str, str]] = []
    email_calls: list[tuple[str, str, str]] = []
    service = NotificationService(
        notification_session,
        telegram_sender=lambda chat, body: telegram_calls.append((chat, body)),
        email_sender=lambda recipient, subject, body: email_calls.append((recipient, subject, body)),
    )
    linked_user = notification_session.query(User).filter(User.username == "notice-manager").one()
    linked_user.telegram_chat_id = "mock-chat-1"
    notification_session.commit()

    result = service.notify("RISK_HIGH", "High risk", "ATM needs cash")

    assert [entry["status"] for entry in result] == ["SENT", "SENT"]
    assert telegram_calls == [("mock-chat-1", "High risk\nATM needs cash")]
    assert email_calls == [("ops@example.test", "High risk", "ATM needs cash")]
    logs = notification_session.query(NotificationDelivery).order_by(NotificationDelivery.channel).all()
    assert {(entry.channel, entry.status) for entry in logs} == {("EMAIL", "SENT"), ("TELEGRAM", "SENT")}


def test_provider_failures_are_logged_without_error_details(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _test_settings(monkeypatch)

    def fail_send(*_args: str) -> None:
        raise RuntimeError("sensitive provider response")

    service = NotificationService(notification_session, telegram_sender=fail_send, email_sender=fail_send)
    linked_user = notification_session.query(User).filter(User.username == "notice-manager").one()
    linked_user.telegram_chat_id = "mock-chat-2"
    notification_session.commit()

    result = service.notify("RISK_CRITICAL", "Critical risk", "ATM needs cash")

    assert [entry["status"] for entry in result] == ["FAILED", "FAILED"]
    assert all(entry.error == "RuntimeError" for entry in notification_session.query(NotificationDelivery).all())
    assert all("sensitive" not in (entry.error or "") for entry in notification_session.query(NotificationDelivery).all())


def test_gmail_api_delivery_refreshes_token_and_sends_to_each_recipient(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class Response:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self.payload

    def fake_post(url: str, **kwargs: object) -> Response:
        calls.append((url, kwargs))
        if url.endswith("/token"):
            return Response({"access_token": "test-access-token"})
        return Response({"id": "sent-message"})

    monkeypatch.setattr(notification_module.httpx, "post", fake_post)
    monkeypatch.setattr(
        notification_module,
        "settings",
        replace(
            notification_module.settings,
            notification_email_provider="gmail_api",
            gmail_api_client_id="client-id",
            gmail_api_client_secret="client-secret",
            gmail_api_refresh_token="refresh-token",
            gmail_api_sender_email="sender@example.test",
            notification_email_recipients=("one@example.test", "two@example.test"),
        ),
    )

    result = NotificationService(notification_session).notify("TEST", "Subject", "Body")

    assert [entry["status"] for entry in result[-2:]] == ["SENT", "SENT"]
    assert [url for url, _kwargs in calls] == [
        "https://oauth2.googleapis.com/token",
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        "https://oauth2.googleapis.com/token",
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
    ]
    token_kwargs = calls[0][1]
    assert token_kwargs["data"]["scope"] == notification_module.GMAIL_SEND_SCOPE  # type: ignore[index]
    api_kwargs = calls[1][1]
    assert api_kwargs["headers"] == {"Authorization": "Bearer test-access-token"}
    raw = api_kwargs["json"]["raw"]  # type: ignore[index]
    assert b"To: one@example.test" in base64.urlsafe_b64decode(str(raw))


def test_gmail_api_failure_is_logged_as_failed_delivery(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        def raise_for_status(self) -> None:
            raise notification_module.httpx.HTTPStatusError(
                "provider failure",
                request=notification_module.httpx.Request("POST", "https://example.test"),
                response=notification_module.httpx.Response(401),
            )

        def json(self) -> dict[str, object]:
            return {"access_token": "test-access-token"}

    monkeypatch.setattr(notification_module.httpx, "post", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(
        notification_module,
        "settings",
        replace(
            notification_module.settings,
            notification_email_provider="gmail_api",
            gmail_api_client_id="client-id",
            gmail_api_client_secret="client-secret",
            gmail_api_refresh_token="refresh-token",
            gmail_api_sender_email="sender@example.test",
            notification_email_recipients=("ops@example.test",),
        ),
    )

    result = NotificationService(notification_session).notify("TEST", "Subject", "Body")

    assert result[-1]["status"] == "FAILED"
    delivery = notification_session.query(NotificationDelivery).filter_by(channel="EMAIL").one()
    assert delivery.error == "RuntimeError"


def test_gmail_api_missing_configuration_does_not_attempt_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notification_module.httpx, "post", lambda *_args, **_kwargs: pytest.fail("network call"))
    monkeypatch.setattr(
        notification_module,
        "settings",
        replace(notification_module.settings, gmail_api_client_id=None),
    )

    with pytest.raises(RuntimeError, match="not configured"):
        notification_module._gmail_api_send("ops@example.test", "Subject", "Body")


def _notification_client(notification_session: Session) -> TestClient:
    def override_get_db() -> Iterator[Session]:
        yield notification_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_test_email_requires_authentication_and_admin_permission(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "phase-nine-notification-test-secret-over-32-characters")
    manager = notification_session.query(User).filter(User.username == "notice-manager").one()
    manager_token = create_access_token(manager.id, manager.token_version)
    try:
        with _notification_client(notification_session) as client:
            assert client.post("/notifications/test-email").status_code == 401
            denied = client.post(
                "/notifications/test-email",
                headers={"Authorization": f"Bearer {manager_token}"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert denied.status_code == 403


def test_admin_test_email_sends_once_to_each_configured_recipient(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "phase-nine-notification-test-secret-over-32-characters")
    _test_settings(monkeypatch, ("ops-one@example.test", "ops-two@example.test", "ops-one@example.test"))
    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        notification_module,
        "_smtp_send",
        lambda recipient, subject, body: sent.append((recipient, subject, body)),
    )
    admin = notification_session.query(User).filter(User.username == "notice-admin").one()
    token = create_access_token(admin.id, admin.token_version)
    try:
        with _notification_client(notification_session) as client:
            response = client.post(
                "/notifications/test-email",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["status"] == "SENT"
    assert response.json()["attempted"] == 2
    assert [recipient for recipient, _, _ in sent] == ["ops-one@example.test", "ops-two@example.test"]
    assert all(subject == "[ATM Cash Intelligence] SMTP test email" for _, subject, _ in sent)
    assert all("diagnostic test email" in body for _, _, body in sent)
    deliveries = notification_session.query(NotificationDelivery).filter(
        NotificationDelivery.event_type == "EMAIL_TEST"
    ).all()
    assert len(deliveries) == 2
    assert {delivery.status for delivery in deliveries} == {"SENT"}


def test_admin_test_email_returns_failure_and_logs_safe_smtp_details(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "phase-nine-notification-test-secret-over-32-characters")
    _test_settings(monkeypatch)

    def fail_send(*_args: str) -> None:
        raise smtplib.SMTPAuthenticationError(535, b"credentials rejected")

    monkeypatch.setattr(notification_module, "_smtp_send", fail_send)
    admin = notification_session.query(User).filter(User.username == "notice-admin").one()
    token = create_access_token(admin.id, admin.token_version)
    try:
        with _notification_client(notification_session) as client:
            with caplog.at_level("WARNING", logger=notification_module.__name__):
                response = client.post(
                    "/notifications/test-email",
                    headers={"Authorization": f"Bearer {token}"},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 502
    assert response.json()["status"] == "FAILED"
    assert response.json()["failed"] == 1
    delivery = notification_session.query(NotificationDelivery).filter(
        NotificationDelivery.event_type == "EMAIL_TEST"
    ).one()
    assert delivery.status == "FAILED"
    log_record = next(record for record in caplog.records if record.message == "email_notification_delivery_failed")
    assert log_record.error_type == "SMTPAuthenticationError"
    assert log_record.smtp_code == 535
    assert "credentials rejected" not in caplog.text


def test_authenticated_telegram_test_sends_only_to_requesting_user_and_logs_delivery(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "phase-nine-notification-test-secret-over-32-characters")
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        notification_module,
        "_telegram_send",
        lambda chat_id, text: sent.append((chat_id, text)),
    )
    requester = notification_session.query(User).filter(User.username == "notice-manager").one()
    requester.telegram_chat_id = "requester-chat"
    other = notification_session.query(User).filter(User.username == "notice-admin").one()
    other.telegram_chat_id = "other-chat"
    notification_session.commit()
    token = create_access_token(requester.id, requester.token_version)

    try:
        with _notification_client(notification_session) as client:
            response = client.post(
                "/notifications/test-telegram",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["status"] == "SENT"
    assert sent == [
        (
            "requester-chat",
            "ATM Cash Intelligence Telegram test\nThis is a Telegram delivery test for your linked account.",
        )
    ]
    deliveries = notification_session.query(NotificationDelivery).filter_by(event_type="TELEGRAM_TEST").all()
    assert len(deliveries) == 1
    assert deliveries[0].channel == "TELEGRAM"
    assert deliveries[0].recipient == "requester-chat"
    assert deliveries[0].status == "SENT"
    assert deliveries[0].error is None


def test_telegram_test_provider_failure_returns_502_and_logs_failed_delivery(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "phase-nine-notification-test-secret-over-32-characters")
    monkeypatch.setattr(
        notification_module,
        "_telegram_send",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("provider response contains no safe details")),
    )
    requester = notification_session.query(User).filter(User.username == "notice-manager").one()
    requester.telegram_chat_id = "requester-chat"
    notification_session.commit()
    token = create_access_token(requester.id, requester.token_version)

    try:
        with _notification_client(notification_session) as client:
            response = client.post(
                "/notifications/test-telegram",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 502
    assert response.json()["status"] == "FAILED"
    delivery = notification_session.query(NotificationDelivery).filter_by(event_type="TELEGRAM_TEST").one()
    assert delivery.recipient == "requester-chat"
    assert delivery.status == "FAILED"
    assert delivery.error == "RuntimeError"


def test_telegram_test_requires_authentication(
    notification_session: Session,
) -> None:
    try:
        with _notification_client(notification_session) as client:
            response = client.post("/notifications/test-telegram")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 401
    assert notification_session.query(NotificationDelivery).filter_by(event_type="TELEGRAM_TEST").count() == 0


def test_telegram_test_rejects_unlinked_account_without_delivery(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "phase-nine-notification-test-secret-over-32-characters")
    sender = lambda *_args: pytest.fail("Telegram provider must not be called")
    monkeypatch.setattr(notification_module, "_telegram_send", sender)
    requester = notification_session.query(User).filter(User.username == "notice-manager").one()
    token = create_access_token(requester.id, requester.token_version)

    try:
        with _notification_client(notification_session) as client:
            response = client.post(
                "/notifications/test-telegram",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 409
    assert response.json()["reason"] == "TELEGRAM_ACCOUNT_NOT_LINKED"
    assert notification_session.query(NotificationDelivery).filter_by(event_type="TELEGRAM_TEST").count() == 0


def test_telegram_test_rejects_inactive_account_before_delivery(
    notification_session: Session,
) -> None:
    requester = notification_session.query(User).filter(User.username == "notice-manager").one()
    requester.telegram_chat_id = "inactive-chat"
    requester.is_active = False
    notification_session.commit()

    with pytest.raises(TelegramTestConfigurationError, match="TELEGRAM_ACCOUNT_INACTIVE"):
        NotificationService(notification_session).send_test_telegram(requester)

    assert notification_session.query(NotificationDelivery).filter_by(event_type="TELEGRAM_TEST").count() == 0


def test_one_time_linking_and_telegram_acknowledgement(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivered: list[tuple[str, str]] = []
    service = NotificationService(notification_session, telegram_sender=lambda chat, body: delivered.append((chat, body)))
    user = notification_session.query(User).filter(User.username == "notice-manager").one()
    link = service.create_link_token(user)
    token = str(link["token"])
    assert service.handle_command("chat-ack", f"/link {token}") == "Telegram account linked successfully."
    assert service.handle_command("chat-ack", f"/link {token}").startswith("Invalid or expired")

    alert = Alert(
        atm_id=notification_session.query(ATM).one().id,
        forecast_id=notification_session.query(Forecast).one().id,
        alert_type="CASH_RISK",
        severity="HIGH",
        status="OPEN",
        message="High risk",
    )
    notification_session.add(alert)
    notification_session.commit()
    notification_session.refresh(alert)

    response = service.handle_command("chat-ack", f"/acknowledge {alert.id}")

    assert response == f"Alert #{alert.id} acknowledged."
    assert alert.status == "ACKNOWLEDGED"
    assert alert.action_source == "TELEGRAM"
    assert alert.acknowledged_by == user.username


def test_telegram_cannot_approve_replenishment(notification_session: Session) -> None:
    user = notification_session.query(User).filter(User.username == "notice-manager").one()
    user.telegram_chat_id = "approval-denial-chat"
    atm = notification_session.query(ATM).one()
    replenishment = Replenishment(
        atm_id=atm.id,
        requested_amount=500.0,
        status="REQUESTED",
        requested_by=user.id,
    )
    notification_session.add(replenishment)
    notification_session.commit()

    response = NotificationService(notification_session).handle_command("approval-denial-chat", "/approve 1")

    assert "web-only" in response
    assert notification_session.query(Replenishment).one().status == "REQUESTED"


def test_link_token_and_acknowledgement_through_telegram_webhook(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "phase-nine-notification-test-secret-over-32-characters")
    monkeypatch.setattr(
        notification_routes,
        "settings",
        replace(notification_routes.settings, telegram_webhook_secret="webhook-test-secret"),
    )
    replies: list[tuple[str, str]] = []
    monkeypatch.setattr(
        notification_module,
        "_telegram_send",
        lambda chat_id, text: replies.append((chat_id, text)),
    )
    user = notification_session.query(User).filter(User.username == "notice-manager").one()
    token = create_access_token(user.id, user.token_version)
    atm = notification_session.query(ATM).one()
    forecast = notification_session.query(Forecast).one()
    alert = Alert(
        atm_id=atm.id,
        forecast_id=forecast.id,
        alert_type="CASH_RISK",
        severity="CRITICAL",
        status="OPEN",
        message="Critical risk",
    )
    notification_session.add(alert)
    notification_session.commit()
    notification_session.refresh(alert)

    def override_get_db() -> Iterator[Session]:
        yield notification_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            link_response = client.post(
                "/notifications/telegram/link-token",
                headers={"Authorization": f"Bearer {token}"},
            )
            link_token = link_response.json()["token"]
            link_update = {
                "message": {"chat": {"id": 12345}, "text": f"/link {link_token}"}
            }
            linked = client.post(
                "/notifications/telegram/webhook",
                json=link_update,
                headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-test-secret"},
            )
            ack_update = {
                "message": {"chat": {"id": 12345}, "text": f"/acknowledge {alert.id}"}
            }
            acknowledged = client.post(
                "/notifications/telegram/webhook",
                json=ack_update,
                headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-test-secret"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    notification_session.refresh(alert)
    assert link_response.status_code == 200
    assert linked.status_code == 200
    assert acknowledged.status_code == 200
    assert alert.status == "ACKNOWLEDGED"
    assert alert.action_source == "TELEGRAM"
    assert replies[-1][1].endswith(f"Alert #{alert.id} acknowledged.")


def test_webhook_secret_requires_a_configured_match() -> None:
    assert verify_webhook_secret("configured-secret", "configured-secret")
    assert not verify_webhook_secret("configured-secret", "wrong-secret")
    assert not verify_webhook_secret(None, "configured-secret")


def test_required_lifecycle_events_dispatch_notifications(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    def record_event(
        self: NotificationService,
        event_type: str,
        _subject: str,
        _message: str,
        **_kwargs: object,
    ):
        events.append(event_type)
        return []

    monkeypatch.setattr(NotificationService, "notify", record_event)
    user = notification_session.query(User).filter(User.username == "notice-manager").one()
    atm = notification_session.query(ATM).one()
    forecast = notification_session.query(Forecast).one()
    alerts = AlertService(notification_session)
    alerts.create_or_update_risk_alert(atm.id, atm.atm_code, forecast.id, "WARNING", 500.0)
    alerts.create_or_update_risk_alert(atm.id, atm.atm_code, forecast.id, "HIGH", 400.0)
    alerts.create_or_update_risk_alert(atm.id, atm.atm_code, forecast.id, "HIGH", 300.0)
    alerts.create_or_update_risk_alert(atm.id, atm.atm_code, forecast.id, "CRITICAL", 100.0)

    replenishments = ReplenishmentService(notification_session)
    draft = replenishments.create(user, atm.atm_code, 500.0, forecast.id, False, None, "WEB")
    replenishments.submit(int(draft["replenishment_id"]), user, "WEB")
    approved_request = replenishments.create(user, atm.atm_code, 600.0, forecast.id, True, None, "WEB")
    approved = replenishments.approve(int(approved_request["replenishment_id"]), user, None, None, "WEB")
    replenishments.schedule(
        int(approved["replenishment_id"]),
        user,
        datetime(2030, 1, 1, tzinfo=timezone.utc),
        None,
        "WEB",
    )
    replenishments.complete(int(approved["replenishment_id"]), user, None, "WEB")
    rejected_request = replenishments.create(user, atm.atm_code, 700.0, forecast.id, True, None, "WEB")
    replenishments.reject(int(rejected_request["replenishment_id"]), user, "Not required", "WEB")

    assert events.count("RISK_HIGH") == 1
    assert events.count("RISK_CRITICAL") == 1
    assert events.count("REPLENISHMENT_REQUESTED") == 3
    assert "REPLENISHMENT_APPROVED" in events
    assert "REPLENISHMENT_REJECTED" in events
    assert "REPLENISHMENT_COMPLETED" in events


def test_automatic_retry_skips_successful_recipients(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _test_settings(monkeypatch, recipients=())
    monkeypatch.setattr(NotificationService, "notify", REAL_NOTIFY)
    first_user = notification_session.query(User).filter(User.username == "notice-manager").one()
    second_user = notification_session.query(User).filter(User.username == "notice-admin").one()
    first_user.telegram_chat_id = "retry-chat-1"
    second_user.telegram_chat_id = "retry-chat-2"
    notification_session.commit()

    calls: list[str] = []
    fail_once = {"retry-chat-2": True}

    def sender(chat_id: str, _body: str) -> None:
        calls.append(chat_id)
        if fail_once.get(chat_id):
            fail_once[chat_id] = False
            raise RuntimeError("provider unavailable")

    service = NotificationService(notification_session, telegram_sender=sender, email_sender=lambda *_args: None)
    first_result = service.notify(
        "RISK_HIGH",
        "High risk",
        "ATM needs cash",
        event_key="RISK_HIGH:retry-alert",
    )
    second_result = service.notify(
        "RISK_HIGH",
        "High risk",
        "ATM needs cash",
        event_key="RISK_HIGH:retry-alert",
    )

    assert [entry["status"] for entry in first_result if entry["channel"] == "TELEGRAM"] == ["SENT", "FAILED"]
    assert [entry["status"] for entry in second_result if entry["channel"] == "TELEGRAM"] == ["SENT", "SENT"]
    assert calls == ["retry-chat-1", "retry-chat-2", "retry-chat-2"]
    deliveries = (
        notification_session.query(NotificationDelivery)
        .filter(NotificationDelivery.channel == "TELEGRAM")
        .all()
    )
    assert len(deliveries) == 2
    assert all(delivery.status == "SENT" for delivery in deliveries)
    assert sorted(delivery.attempts for delivery in deliveries) == [1, 2]


def test_total_provider_failure_can_succeed_on_bounded_retry(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _test_settings(monkeypatch, recipients=())
    monkeypatch.setattr(NotificationService, "notify", REAL_NOTIFY)
    user = notification_session.query(User).filter(User.username == "notice-manager").one()
    user.telegram_chat_id = "total-retry-chat"
    notification_session.commit()
    calls = {"count": 0}

    def sender(_chat_id: str, _body: str) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary provider failure")

    service = NotificationService(notification_session, telegram_sender=sender, email_sender=lambda *_args: None)
    first = service.notify("RISK_CRITICAL", "Critical risk", "ATM needs cash", event_key="RISK_CRITICAL:retry")
    second = service.notify("RISK_CRITICAL", "Critical risk", "ATM needs cash", event_key="RISK_CRITICAL:retry")

    assert [entry["status"] for entry in first if entry["channel"] == "TELEGRAM"] == ["FAILED"]
    assert [entry["status"] for entry in second if entry["channel"] == "TELEGRAM"] == ["SENT"]
    delivery = notification_session.query(NotificationDelivery).filter_by(channel="TELEGRAM").one()
    assert delivery.status == "SENT"
    assert delivery.attempts == 2


def test_worker_retries_failed_notification_and_marks_success(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = queue_module.enqueue_job(
        notification_session,
        "notification.delivery",
        {
            "event_key": "RISK_HIGH:worker-retry",
            "event_type": "RISK_HIGH",
            "subject": "High risk",
            "message": "ATM needs cash",
        },
        dedupe_key="RISK_HIGH:worker-retry",
        max_attempts=2,
    )
    outcomes = [[{"status": "FAILED"}], [{"status": "SENT"}]]

    class FakeNotificationService:
        def __init__(self, _session: Session):
            pass

        def notify(self, *_args: object, **_kwargs: object) -> list[dict[str, object]]:
            return outcomes.pop(0)

    monkeypatch.setattr(worker_module, "SessionLocal", lambda: notification_session)
    monkeypatch.setattr(worker_module, "NotificationService", FakeNotificationService)

    assert worker_module.process_one()
    notification_session.expire_all()
    assert notification_session.get(BackgroundJob, job.id).status == "RETRY"
    retried_job = notification_session.get(BackgroundJob, job.id)
    assert retried_job is not None
    retried_job.available_at = datetime.now(timezone.utc)
    notification_session.commit()

    assert worker_module.process_one()
    notification_session.expire_all()
    assert notification_session.get(BackgroundJob, job.id).status == "SUCCEEDED"


def test_worker_marks_permanent_notification_failure_after_retry_limit(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = queue_module.enqueue_job(
        notification_session,
        "notification.delivery",
        {
            "event_key": "RISK_CRITICAL:worker-failure",
            "event_type": "RISK_CRITICAL",
            "subject": "Critical risk",
            "message": "ATM needs cash",
        },
        dedupe_key="RISK_CRITICAL:worker-failure",
        max_attempts=2,
    )

    class FailedNotificationService:
        def __init__(self, _session: Session):
            pass

        def notify(self, *_args: object, **_kwargs: object) -> list[dict[str, object]]:
            return [{"status": "FAILED"}]

    monkeypatch.setattr(worker_module, "SessionLocal", lambda: notification_session)
    monkeypatch.setattr(worker_module, "NotificationService", FailedNotificationService)

    assert worker_module.process_one()
    failed_job = notification_session.get(BackgroundJob, job.id)
    assert failed_job is not None
    failed_job.available_at = datetime.now(timezone.utc)
    notification_session.commit()
    assert worker_module.process_one()
    notification_session.expire_all()
    assert notification_session.get(BackgroundJob, job.id).status == "FAILED"


def test_outbox_recovers_when_queue_insertion_fails(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outbox = queue_module.stage_notification(
        notification_session,
        "REPLENISHMENT_REQUESTED:42",
        "REPLENISHMENT_REQUESTED",
        "Replenishment requested",
        "ATM needs cash",
    )
    notification_session.commit()
    original_add = notification_session.add

    def fail_background_job_add(instance: object) -> None:
        if isinstance(instance, BackgroundJob):
            raise RuntimeError("queue temporarily unavailable")
        original_add(instance)

    monkeypatch.setattr(notification_session, "add", fail_background_job_add)
    assert queue_module.dispatch_outbox_once(notification_session)
    notification_session.expire_all()
    assert notification_session.get(NotificationOutbox, outbox.id).status == "RETRY"

    monkeypatch.setattr(notification_session, "add", original_add)
    retry_outbox = notification_session.get(NotificationOutbox, outbox.id)
    assert retry_outbox is not None
    retry_outbox.available_at = datetime.now(timezone.utc)
    notification_session.commit()
    assert queue_module.dispatch_outbox_once(notification_session)
    notification_session.expire_all()
    assert notification_session.get(NotificationOutbox, outbox.id).status == "DISPATCHED"
    assert notification_session.query(BackgroundJob).filter_by(dedupe_key="REPLENISHMENT_REQUESTED:42").count() == 1


def test_alert_and_replenishment_stage_outbox_in_async_mode(
    notification_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async_settings = replace(config_module.settings, async_notifications=True)
    monkeypatch.setattr(config_module, "settings", async_settings)
    monkeypatch.setattr(replenishment_module, "settings", async_settings)
    user = notification_session.query(User).filter(User.username == "notice-manager").one()
    atm = notification_session.query(ATM).one()
    forecast = notification_session.query(Forecast).one()

    alert = AlertService(notification_session).create_or_update_risk_alert(
        atm.id,
        atm.atm_code,
        forecast.id,
        "HIGH",
        400.0,
    )
    request = ReplenishmentService(notification_session).create(
        user,
        atm.atm_code,
        500.0,
        forecast.id,
        True,
        None,
        "WEB",
    )

    assert alert is not None
    assert notification_session.query(NotificationOutbox).count() == 2
    assert notification_session.query(NotificationOutbox).filter_by(event_key=f"RISK_HIGH:{alert.id}").one()
    assert notification_session.query(NotificationOutbox).filter_by(
        event_key=f"REPLENISHMENT_REQUESTED:{request['replenishment_id']}"
    ).one()


def test_stale_processing_job_is_recovered(
    notification_session: Session,
) -> None:
    job = queue_module.enqueue_job(
        notification_session,
        "notification.delivery",
        {"event_type": "TEST", "subject": "Test", "message": "Body"},
        dedupe_key="stale-job",
        max_attempts=3,
    )
    job.status = "PROCESSING"
    job.attempts = 1
    job.locked_at = datetime.now(timezone.utc).replace(year=2020)
    notification_session.commit()

    claimed = queue_module.claim_job(notification_session)

    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == "PROCESSING"
    assert claimed.attempts == 2
    assert claimed.claim_token is not None


def test_expired_job_claim_cannot_finalize_after_recovery(
    notification_session: Session,
) -> None:
    job = queue_module.enqueue_job(
        notification_session,
        "notification.delivery",
        {"event_type": "TEST", "subject": "Test", "message": "Body"},
        dedupe_key="fenced-job",
        max_attempts=3,
    )
    job.status = "PROCESSING"
    job.attempts = 1
    job.locked_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    job.claim_token = "expired-worker"
    notification_session.commit()

    reclaimed = queue_module.claim_job(notification_session)
    assert reclaimed is not None
    assert reclaimed.claim_token not in {None, "expired-worker"}

    assert not queue_module.mark_job_succeeded(notification_session, job.id, "expired-worker")
    notification_session.expire_all()
    current = notification_session.get(BackgroundJob, job.id)
    assert current is not None
    assert current.status == "PROCESSING"

    assert queue_module.mark_job_failed(
        notification_session,
        job.id,
        "RuntimeError",
        claim_token=reclaimed.claim_token,
    )
    notification_session.expire_all()
    assert notification_session.get(BackgroundJob, job.id).status == "RETRY"


def test_expired_delivery_claim_cannot_overwrite_newer_result(
    notification_session: Session,
) -> None:
    repository = NotificationRepository(notification_session)
    first, should_send = repository.claim_delivery(
        "RISK_HIGH",
        "TELEGRAM",
        "fenced-chat",
        "fenced-delivery",
    )
    assert should_send
    assert first.claim_token is not None
    old_token = first.claim_token
    first.locked_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    notification_session.commit()

    second, should_send = repository.claim_delivery(
        "RISK_HIGH",
        "TELEGRAM",
        "fenced-chat",
        "fenced-delivery",
    )
    assert should_send
    assert second.claim_token not in {None, old_token}

    stale_result = repository.finish_delivery(
        first.id,
        "FAILED",
        "RuntimeError",
        claim_token=old_token,
    )
    assert stale_result.status == "PROCESSING"

    final = repository.finish_delivery(
        second.id,
        "SENT",
        claim_token=second.claim_token,
    )
    assert final.status == "SENT"


def test_expired_outbox_claim_cannot_overwrite_newer_state(
    notification_session: Session,
) -> None:
    outbox = queue_module.stage_notification(
        notification_session,
        "RISK_HIGH:fenced-outbox",
        "RISK_HIGH",
        "High risk",
        "ATM needs cash",
    )
    notification_session.commit()
    outbox.status = "PROCESSING"
    outbox.attempts = 1
    outbox.locked_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    outbox.claim_token = "expired-outbox-worker"
    notification_session.commit()

    queue_module._recover_stale_outbox(notification_session, datetime.now(timezone.utc))
    current = notification_session.get(NotificationOutbox, outbox.id)
    assert current is not None
    assert current.status == "RETRY"
    assert current.claim_token is None

    current.status = "PROCESSING"
    current.locked_at = datetime.now(timezone.utc)
    current.claim_token = "newer-outbox-worker"
    notification_session.commit()

    queue_module._mark_outbox_dispatch_failed(
        notification_session,
        outbox.id,
        "expired-outbox-worker",
        "RuntimeError",
    )
    notification_session.expire_all()
    current = notification_session.get(NotificationOutbox, outbox.id)
    assert current is not None
    assert current.status == "PROCESSING"
    assert current.claim_token == "newer-outbox-worker"


def test_duplicate_outbox_staging_preserves_callers_transaction(
    notification_session: Session,
) -> None:
    first = queue_module.stage_notification(
        notification_session,
        "RISK_HIGH:atomic-event",
        "RISK_HIGH",
        "High risk",
        "ATM needs cash",
    )
    notification_session.commit()

    marker = Replenishment(
        atm_id=notification_session.query(ATM).one().id,
        requested_amount=123.0,
        status="DRAFT",
        requested_by=notification_session.query(User).filter(User.username == "notice-manager").one().id,
    )
    notification_session.add(marker)
    duplicate = queue_module.stage_notification(
        notification_session,
        "RISK_HIGH:atomic-event",
        "RISK_HIGH",
        "Changed subject must not replace original",
        "Changed message must not replace original",
    )
    notification_session.commit()

    assert duplicate.id == first.id
    assert notification_session.get(Replenishment, marker.id) is not None
    assert notification_session.query(NotificationOutbox).filter_by(event_key="RISK_HIGH:atomic-event").count() == 1
