from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from app.core.permissions import ROLE_DESCRIPTIONS
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.atm import ATM, Forecast
from app.models.auth import Role, User
from app.realtime import ConnectedClient, ConnectionManager, connection_manager
from app.services.alert_service import AlertService
from app.services.notification_service import NotificationService
from app.services.replenishment_service import ReplenishmentService


class FakeWebSocket:
    def __init__(self, fail_send: bool = False) -> None:
        self.accepted_protocol: str | None = None
        self.events: list[dict[str, object]] = []
        self.fail_send = fail_send

    async def accept(self, subprotocol: str | None = None) -> None:
        self.accepted_protocol = subprotocol

    async def send_json(self, event: dict[str, object]) -> None:
        if self.fail_send:
            raise RuntimeError("client disconnected")
        self.events.append(event)


@pytest.fixture
def realtime_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Session, User, ATM, Forecast, str]]:
    monkeypatch.setenv("JWT_SECRET_KEY", "phase-ten-realtime-test-secret-at-least-32-characters")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = Session(engine)

    manager_role = Role(name="BANK_MANAGER", description=ROLE_DESCRIPTIONS["BANK_MANAGER"])
    session.add(manager_role)
    session.commit()
    user = User(username="realtime-manager", password_hash="test-only", role_id=manager_role.id)
    atm = ATM(
        atm_code="ATM-REALTIME",
        branch_id="BRANCH-REALTIME",
        region="TEST",
        capacity=10000.0,
        current_cash=4000.0,
        daily_demand=1000.0,
    )
    session.add_all([user, atm])
    session.commit()
    session.refresh(user)
    session.refresh(atm)
    forecast = Forecast(
        atm_id=atm.id,
        forecast_date=datetime.now(timezone.utc),
        predicted_demand=1300.0,
        risk_level="HIGH",
        recommended_top_up=1500.0,
        model_version="test",
    )
    session.add(forecast)
    session.commit()
    session.refresh(forecast)
    token = create_access_token(user.id, user.token_version)

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(NotificationService, "notify", lambda *_args, **_kwargs: [])
    try:
        with TestClient(app) as client:
            yield client, session, user, atm, forecast, token
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_connection_manager_tracks_clients_broadcasts_and_disconnects() -> None:
    manager = ConnectionManager()
    first = FakeWebSocket()
    second = FakeWebSocket()
    event = {"event_type": "alert.created", "entity_id": "7"}

    async def run() -> None:
        await manager.connect(first, 1, "one", "BANK_MANAGER")
        await manager.connect(second, 2, "two", "ANALYST")
        assert first.accepted_protocol == "atm-events"
        assert manager.client_count == 2
        assert {user.user_id for user in manager.connected_users} == {1, 2}
        await manager.broadcast(event)
        manager.disconnect(first)
        await manager.broadcast({"event_type": "alert.resolved"})

    asyncio.run(run())

    assert first.events == [event]
    assert second.events == [event, {"event_type": "alert.resolved"}]
    assert manager.client_count == 1


def test_connection_manager_removes_failed_client_without_raising() -> None:
    manager = ConnectionManager()
    disconnected = FakeWebSocket(fail_send=True)

    async def run() -> None:
        await manager.connect(disconnected, 1, "one", "BANK_MANAGER")
        await manager.broadcast({"event_type": "alert.created"})

    asyncio.run(run())

    assert manager.client_count == 0


def test_websocket_rejects_unauthorized_connection(realtime_environment) -> None:
    client, *_ = realtime_environment

    with pytest.raises(WebSocketDisconnect) as disconnect:
        with client.websocket_connect("/ws/events", subprotocols=["atm-events", "bearer.invalid-token"]):
            pass

    assert disconnect.value.code == 1008


def test_alert_and_replenishment_events_reach_authenticated_clients(realtime_environment) -> None:
    client, session, user, atm, forecast, token = realtime_environment
    protocols = ["atm-events", f"bearer.{token}"]
    baseline_clients = connection_manager.client_count

    with client.websocket_connect("/ws/events", subprotocols=protocols) as first:
        with client.websocket_connect("/ws/events", subprotocols=protocols) as second:
            alert = AlertService(session).create_or_update_risk_alert(
                atm.id, atm.atm_code, forecast.id, "WARNING", 100.0
            )
            assert alert is not None
            first_alert_event = first.receive_json()
            second_alert_event = second.receive_json()

            request = ReplenishmentService(session).create(
                user,
                atm.atm_code,
                500.0,
                forecast.id,
                True,
                None,
                "WEB",
            )
            first_replenishment_event = first.receive_json()
            second_replenishment_event = second.receive_json()

            for event in (first_alert_event, second_alert_event):
                assert event["event_type"] == "alert.created"
                assert event["entity_type"] == "ALERT"
                assert event["entity_id"] == str(alert.id)
                assert event["atm_id"] == atm.atm_code
                assert event["timestamp"]
                assert event["status"] == "OPEN"
                assert event["severity"] == "WARNING"
                assert event["source"] == "SYSTEM"
            for event in (first_replenishment_event, second_replenishment_event):
                assert event["event_type"] == "replenishment.requested"
                assert event["entity_type"] == "REPLENISHMENT"
                assert event["entity_id"] == str(request["replenishment_id"])
                assert event["atm_id"] == atm.atm_code
                assert event["timestamp"]
                assert event["status"] == "REQUESTED"
                assert event["source"] == "WEB"

            alert_service = AlertService(session)
            alert_service.acknowledge(alert.id, user.username, "WEB", user_id=user.id)
            acknowledged_event = first.receive_json()
            assert acknowledged_event["event_type"] == "alert.acknowledged"
            assert acknowledged_event["entity_id"] == str(alert.id)
            assert acknowledged_event["status"] == "ACKNOWLEDGED"
            alert_service.resolve(alert.id, user.username, "WEB", user_id=user.id)
            resolved_event = first.receive_json()
            assert resolved_event["event_type"] == "alert.resolved"
            assert resolved_event["status"] == "RESOLVED"

            replenishment_service = ReplenishmentService(session)
            replenishment_id = int(request["replenishment_id"])
            replenishment_service.approve(replenishment_id, user, None, None, "WEB")
            approval_event = first.receive_json()
            assert approval_event["event_type"] == "replenishment.approved"
            assert approval_event["status"] == "APPROVED"
            replenishment_service.schedule(
                replenishment_id,
                user,
                datetime(2030, 1, 1, tzinfo=timezone.utc),
                None,
                "WEB",
            )
            scheduling_event = first.receive_json()
            assert scheduling_event["event_type"] == "replenishment.scheduled"
            assert scheduling_event["status"] == "SCHEDULED"
            replenishment_service.complete(replenishment_id, user, None, "WEB")
            completion_event = first.receive_json()
            assert completion_event["event_type"] == "replenishment.completed"
            assert completion_event["status"] == "COMPLETED"

            rejected_request = replenishment_service.create(
                user,
                atm.atm_code,
                400.0,
                forecast.id,
                True,
                None,
                "WEB",
            )
            first.receive_json()
            replenishment_service.reject(
                int(rejected_request["replenishment_id"]), user, "No longer needed", "WEB"
            )
            rejection_event = first.receive_json()
            assert rejection_event["event_type"] == "replenishment.rejected"
            assert rejection_event["status"] == "REJECTED"

    assert connection_manager.client_count == baseline_clients