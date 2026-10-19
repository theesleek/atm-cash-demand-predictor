from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime, timezone
import smtplib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.permissions import ROLE_DESCRIPTIONS
from app.db.base import Base
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.atm import ATM, Alert, Forecast
from app.models.auth import Role, User
from app.models.notification import NotificationDelivery
from app.models.replenishment import Replenishment
from app.services import notification_service as notification_module
from app.api.routes import notifications as notification_routes
from app.services.alert_service import AlertService
from app.services.notification_service import NotificationService, verify_webhook_secret
from app.services.replenishment_service import ReplenishmentService


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

    def record_event(self: NotificationService, event_type: str, _subject: str, _message: str):
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
