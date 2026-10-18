from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.passwords import hash_password
from app.core.permissions import ROLE_DESCRIPTIONS
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.atm import ATM, CashInventory, Forecast
from app.models.auth import AuditLog, Role, User
from app.services.notification_service import NotificationService

TEST_PASSWORD = "phase-eight-replenishment-test-password"


@pytest.fixture(autouse=True)
def mock_notifications(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(NotificationService, "notify", lambda *_args, **_kwargs: [])


@pytest.fixture
def replenishment_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, Session, dict[str, User], ATM, Forecast]]:
    monkeypatch.setenv("JWT_SECRET_KEY", "phase-eight-replenishment-jwt-secret-at-least-32-chars")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = Session(engine)

    roles: dict[str, Role] = {}
    for name, description in ROLE_DESCRIPTIONS.items():
        role = Role(name=name, description=description)
        session.add(role)
        roles[name] = role
    session.commit()

    users: dict[str, User] = {}
    for name, role in roles.items():
        user = User(
            username=f"phase8-{name.lower()}",
            password_hash=hash_password(TEST_PASSWORD),
            role_id=role.id,
        )
        session.add(user)
        users[name] = user
    session.commit()
    for user in users.values():
        session.refresh(user)

    atm = ATM(
        atm_code="ATM-PHASE8",
        branch_id="BRANCH-PHASE8",
        region="TEST",
        capacity=10000.0,
        current_cash=1000.0,
        daily_demand=500.0,
    )
    session.add(atm)
    session.commit()
    forecast = Forecast(
        atm_id=atm.id,
        forecast_date=datetime(2026, 9, 30, tzinfo=timezone.utc),
        predicted_demand=1200.0,
        risk_level="CRITICAL",
        recommended_top_up=1500.0,
        model_version="phase5-test",
    )
    inventory = CashInventory(
        atm_id=atm.id,
        cash_on_hand=1000.0,
        capacity=10000.0,
        status="healthy",
    )
    session.add_all([forecast, inventory])
    session.commit()
    session.refresh(forecast)

    tokens = {name: create_access_token(user.id, user.token_version) for name, user in users.items()}

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            client.headers["X-Action-Source"] = "WEB"
            yield client, session, users, atm, forecast
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _headers(token: str, source: str = "WEB") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Action-Source": source}


def test_officer_creates_request_from_forecast_recommendation(replenishment_environment) -> None:
    client, session, users, atm, forecast = replenishment_environment
    token = create_access_token(users["OPERATIONS_OFFICER"].id, users["OPERATIONS_OFFICER"].token_version)

    created = client.post(
        "/replenishments",
        json={"atm_id": atm.atm_code, "forecast_id": forecast.id},
        headers=_headers(token),
    )

    assert created.status_code == 201
    request = created.json()
    assert request["status"] == "REQUESTED"
    assert request["requested_amount"] == forecast.recommended_top_up
    assert request["forecast_id"] == forecast.id
    assert request["requested_by"] == users["OPERATIONS_OFFICER"].id
    assert client.get("/replenishments", headers=_headers(token)).json()[0]["replenishment_id"] == request[
        "replenishment_id"
    ]
    audit = session.query(AuditLog).filter(AuditLog.entity_type == "REPLENISHMENT").one()
    assert audit.user_id == users["OPERATIONS_OFFICER"].id
    assert audit.action == "REPLENISHMENT_CREATED"


def test_analyst_and_viewer_cannot_create_requests(replenishment_environment) -> None:
    client, _, users, atm, _ = replenishment_environment

    for role_name in ("ANALYST", "VIEWER"):
        user = users[role_name]
        token = create_access_token(user.id, user.token_version)
        response = client.post(
            "/replenishments",
            json={"atm_id": atm.atm_code, "requested_amount": 500.0},
            headers=_headers(token),
        )
        assert response.status_code == 403


def test_manager_approves_web_only_then_schedule_and_complete(replenishment_environment) -> None:
    client, session, users, atm, forecast = replenishment_environment
    officer_token = create_access_token(
        users["OPERATIONS_OFFICER"].id,
        users["OPERATIONS_OFFICER"].token_version,
    )
    manager_token = create_access_token(users["BANK_MANAGER"].id, users["BANK_MANAGER"].token_version)
    created = client.post(
        "/replenishments",
        json={"atm_id": atm.atm_code, "requested_amount": 1800.0, "forecast_id": forecast.id},
        headers=_headers(officer_token),
    )
    replenishment_id = created.json()["replenishment_id"]
    manager_requests = client.get("/replenishments", headers=_headers(manager_token))
    manager_detail = client.get(f"/replenishments/{replenishment_id}", headers=_headers(manager_token))
    assert manager_requests.status_code == 200
    assert manager_requests.json()[0]["replenishment_id"] == replenishment_id
    assert manager_detail.status_code == 200

    api_approval = client.post(
        f"/replenishments/{replenishment_id}/approve",
        json={"approved_amount": 1700.0},
        headers=_headers(manager_token, "API"),
    )
    assert api_approval.status_code == 403

    approved = client.post(
        f"/replenishments/{replenishment_id}/approve",
        json={"approved_amount": 1700.0, "notes": "Adjusted to dispatch amount"},
        headers=_headers(manager_token),
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["approved_amount"] == 1700.0
    assert approved.json()["approved_by"] == users["BANK_MANAGER"].id
    assert approved.json()["approved_at"] is not None

    scheduled = client.post(
        f"/replenishments/{replenishment_id}/schedule",
        json={"scheduled_at": "2030-10-01T08:00:00Z"},
        headers=_headers(officer_token, "API"),
    )
    assert scheduled.status_code == 200
    assert scheduled.json()["status"] == "SCHEDULED"
    assert scheduled.json()["scheduled_at"].startswith("2030-10-01T08:00:00")

    completed = client.post(
        f"/replenishments/{replenishment_id}/complete",
        json={"notes": "Cash loaded"},
        headers=_headers(officer_token, "API"),
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["completed_at"] is not None

    actions = {
        entry.action
        for entry in session.query(AuditLog)
        .filter(AuditLog.entity_type == "REPLENISHMENT", AuditLog.entity_id == str(replenishment_id))
        .all()
    }
    assert actions == {
        "REPLENISHMENT_CREATED",
        "REPLENISHMENT_APPROVED",
        "REPLENISHMENT_SCHEDULED",
        "REPLENISHMENT_COMPLETED",
    }

    audit_response = client.get(
        f"/replenishments/{replenishment_id}/audit",
        headers=_headers(manager_token),
    )
    assert audit_response.status_code == 200
    assert [entry["action"] for entry in audit_response.json()] == [
        "REPLENISHMENT_CREATED",
        "REPLENISHMENT_APPROVED",
        "REPLENISHMENT_SCHEDULED",
        "REPLENISHMENT_COMPLETED",
    ]
    assert audit_response.json()[1]["username"] == users["BANK_MANAGER"].username


def test_officer_cannot_approve_and_manager_can_reject(replenishment_environment) -> None:
    client, _, users, atm, _ = replenishment_environment
    officer_token = create_access_token(
        users["OPERATIONS_OFFICER"].id,
        users["OPERATIONS_OFFICER"].token_version,
    )
    manager_token = create_access_token(users["BANK_MANAGER"].id, users["BANK_MANAGER"].token_version)
    created = client.post(
        "/replenishments",
        json={"atm_id": atm.atm_code, "requested_amount": 1000.0},
        headers=_headers(officer_token),
    )
    replenishment_id = created.json()["replenishment_id"]

    denied_approval = client.post(
        f"/replenishments/{replenishment_id}/approve",
        json={},
        headers=_headers(officer_token),
    )
    rejected = client.post(
        f"/replenishments/{replenishment_id}/reject",
        json={"reason": "Insufficient operational justification"},
        headers=_headers(manager_token, "API"),
    )

    assert denied_approval.status_code == 403
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["approved_by"] is None
    assert rejected.json()["reason"] == "Insufficient operational justification"


def test_amount_capacity_and_invalid_state_rules(replenishment_environment) -> None:
    client, _, users, atm, _ = replenishment_environment
    officer = users["OPERATIONS_OFFICER"]
    manager = users["BANK_MANAGER"]
    officer_token = create_access_token(officer.id, officer.token_version)
    manager_token = create_access_token(manager.id, manager.token_version)

    too_large_request = client.post(
        "/replenishments",
        json={"atm_id": atm.atm_code, "requested_amount": 10000.01},
        headers=_headers(officer_token),
    )
    created = client.post(
        "/replenishments",
        json={"atm_id": atm.atm_code, "requested_amount": 2000.0},
        headers=_headers(officer_token),
    )
    replenishment_id = created.json()["replenishment_id"]
    schedule_early = client.post(
        f"/replenishments/{replenishment_id}/schedule",
        json={"scheduled_at": "2030-10-01T08:00:00Z"},
        headers=_headers(officer_token),
    )
    too_large_approval = client.post(
        f"/replenishments/{replenishment_id}/approve",
        json={"approved_amount": 10000.01},
        headers=_headers(manager_token),
    )
    approved = client.post(
        f"/replenishments/{replenishment_id}/approve",
        json={},
        headers=_headers(manager_token),
    )
    approve_twice = client.post(
        f"/replenishments/{replenishment_id}/approve",
        json={},
        headers=_headers(manager_token),
    )
    complete_early = client.post(
        f"/replenishments/{replenishment_id}/complete",
        json={},
        headers=_headers(officer_token),
    )

    assert too_large_request.status_code == 422
    assert schedule_early.status_code == 409
    assert too_large_approval.status_code == 422
    assert approved.status_code == 200
    assert approve_twice.status_code == 409
    assert complete_early.status_code == 409


def test_draft_can_be_submitted_and_other_request_ids_are_hidden(replenishment_environment) -> None:
    client, session, users, atm, _ = replenishment_environment
    officer = users["OPERATIONS_OFFICER"]
    token = create_access_token(officer.id, officer.token_version)
    other_officer = User(
        username="phase8-other-operator",
        password_hash=hash_password(TEST_PASSWORD),
        role_id=officer.role_id,
    )
    session.add(other_officer)
    session.commit()
    session.refresh(other_officer)
    other_token = create_access_token(other_officer.id, other_officer.token_version)
    created = client.post(
        "/replenishments",
        json={"atm_id": atm.atm_code, "requested_amount": 600.0, "submit": False},
        headers=_headers(token),
    )
    replenishment_id = created.json()["replenishment_id"]
    assert created.json()["status"] == "DRAFT"

    submitted = client.post(f"/replenishments/{replenishment_id}/submit", headers=_headers(token))
    hidden_detail = client.get(f"/replenishments/{replenishment_id}", headers=_headers(other_token))
    own_list = client.get("/replenishments", headers=_headers(other_token))

    assert submitted.status_code == 200
    assert submitted.json()["status"] == "REQUESTED"
    assert hidden_detail.status_code == 404
    assert own_list.json() == []


def test_request_owner_can_cancel_draft(replenishment_environment) -> None:
    client, _, users, atm, _ = replenishment_environment
    officer = users["OPERATIONS_OFFICER"]
    token = create_access_token(officer.id, officer.token_version)
    created = client.post(
        "/replenishments",
        json={"atm_id": atm.atm_code, "requested_amount": 600.0, "submit": False},
        headers=_headers(token),
    )

    cancelled = client.post(
        f"/replenishments/{created.json()['replenishment_id']}/cancel",
        headers=_headers(token),
    )

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
