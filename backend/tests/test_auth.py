from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.passwords import hash_password, verify_password
from app.core.permissions import PERMISSIONS_BY_ROLE, ROLE_DESCRIPTIONS, has_permission
from app.core.security import require_web_approval
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.auth import AuditLog, Role, User

TEST_SECRET = "phase-seven-test-jwt-signing-secret-at-least-32-chars"
TEST_PASSWORD = "phase-seven-valid-test-password"


@pytest.fixture
def auth_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Session, dict[str, User]]]:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    roles: dict[str, Role] = {}
    for role_name, description in ROLE_DESCRIPTIONS.items():
        role = Role(name=role_name, description=description)
        session.add(role)
        roles[role_name] = role
    session.commit()

    users: dict[str, User] = {}
    for role_name, role in roles.items():
        user = User(
            username=role_name.lower(),
            password_hash=hash_password(TEST_PASSWORD),
            role_id=role.id,
        )
        session.add(user)
        users[role_name] = user
    session.commit()
    for user in users.values():
        session.refresh(user)

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client, session, users
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _login(client: TestClient, username: str) -> str:
    response = client.post(
        "/auth/login",
        json={"username": username.lower(), "password": TEST_PASSWORD},
        headers={"X-Action-Source": "WEB"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_login_preflight_allows_cloudflare_frontend(auth_environment) -> None:
    client, _, _ = auth_environment

    response = client.options(
        "/auth/login",
        headers={
            "Origin": "https://atm-cash-demand-predictor.pages.dev",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-action-source",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://atm-cash-demand-predictor.pages.dev"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "OPTIONS" in response.headers["access-control-allow-methods"]
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "content-type" in allowed_headers
    assert "x-action-source" in allowed_headers


def test_successful_login_returns_expiring_token_and_audit(auth_environment) -> None:
    client, session, _ = auth_environment

    response = client.post(
        "/auth/login",
        json={"username": "viewer", "password": TEST_PASSWORD},
        headers={
            "Origin": "https://atm-cash-demand-predictor.pages.dev",
            "X-Action-Source": "WEB",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://atm-cash-demand-predictor.pages.dev"
    assert response.headers["access-control-allow-credentials"] == "true"
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] > 0
    assert payload["user"]["role"] == "VIEWER"
    assert payload["user"]["name"] is None
    assert payload["user"]["last_login_at"]
    assert payload["user"].get("password_hash") is None
    assert "access_token" not in payload["user"]
    audit = session.query(AuditLog).filter(AuditLog.action == "LOGIN_SUCCEEDED").one()
    assert audit.user_id == payload["user"]["user_id"]
    assert audit.source == "WEB"
    current_user = client.get("/auth/me", headers={"Authorization": f"Bearer {payload['access_token']}"})
    assert current_user.status_code == 200
    assert current_user.json()["last_login_at"] == payload["user"]["last_login_at"]


def test_invalid_credentials_are_rejected_and_audited(auth_environment) -> None:
    client, session, _ = auth_environment

    response = client.post(
        "/auth/login",
        json={"username": "viewer", "password": "incorrect-password"},
    )

    assert response.status_code == 401
    assert session.query(AuditLog).filter(AuditLog.action == "LOGIN_FAILED").count() == 1


def test_protected_endpoint_rejects_missing_token_and_accepts_valid_token(auth_environment) -> None:
    client, _, _ = auth_environment

    assert client.get("/alerts").status_code == 401
    token = _login(client, "viewer")
    response = client.get("/alerts", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == []


def test_logout_invalidates_previously_issued_tokens(auth_environment) -> None:
    client, _, _ = auth_environment
    token = _login(client, "viewer")
    headers = {"Authorization": f"Bearer {token}", "X-Action-Source": "WEB"}

    response = client.post("/auth/logout", headers=headers)
    current_user = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 204
    assert current_user.status_code == 401


def test_role_permission_matrix_and_web_only_manager_approval(auth_environment) -> None:
    _, _, users = auth_environment

    assert has_permission("BANK_MANAGER", "replenishments:approve")
    assert not has_permission("OPERATIONS_OFFICER", "replenishments:approve")
    assert has_permission("SUPER_ADMIN", "users:manage")
    assert not has_permission("BANK_MANAGER", "users:manage")
    assert has_permission("VIEWER", "alerts:read")
    assert not has_permission("VIEWER", "alerts:acknowledge")
    assert not has_permission("ANALYST", "alerts:resolve")
    assert not has_permission("ANALYST", "replenishments:create")

    manager_guard = require_web_approval()
    assert manager_guard(user=users["BANK_MANAGER"], action_source="WEB") is users["BANK_MANAGER"]
    with pytest.raises(HTTPException) as api_source_error:
        manager_guard(user=users["BANK_MANAGER"], action_source="API")
    assert api_source_error.value.status_code == 403
    with pytest.raises(HTTPException) as viewer_error:
        manager_guard(user=users["VIEWER"], action_source="WEB")
    assert viewer_error.value.status_code == 403


def test_viewer_and_analyst_are_read_only(auth_environment) -> None:
    client, _, _ = auth_environment
    viewer_token = _login(client, "viewer")
    analyst_token = _login(client, "analyst")

    viewer_alerts = client.get("/alerts", headers={"Authorization": f"Bearer {viewer_token}"})
    viewer_ack = client.post(
        "/alerts/1/acknowledge",
        json={"source": "WEB"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    analyst_alerts = client.get("/alerts", headers={"Authorization": f"Bearer {analyst_token}"})
    analyst_resolve = client.post(
        "/alerts/1/resolve",
        json={"source": "API"},
        headers={"Authorization": f"Bearer {analyst_token}"},
    )

    assert viewer_alerts.status_code == 200
    assert viewer_ack.status_code == 403
    assert analyst_alerts.status_code == 200
    assert analyst_resolve.status_code == 403


def test_user_management_is_admin_only_and_audited(auth_environment) -> None:
    client, session, _ = auth_environment
    manager_token = _login(client, "bank_manager")
    denied = client.post(
        "/auth/users",
        json={"username": "new-viewer", "password": TEST_PASSWORD, "role": "VIEWER"},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert denied.status_code == 403

    admin_token = _login(client, "super_admin")
    created = client.post(
        "/auth/users",
        json={"username": "new-viewer", "password": TEST_PASSWORD, "role": "VIEWER"},
        headers={"Authorization": f"Bearer {admin_token}", "X-Action-Source": "WEB"},
    )

    assert created.status_code == 201
    assert created.json()["role"] == "VIEWER"
    created_user = session.query(User).filter(User.username == "new-viewer").one()
    assert created_user.password_hash != TEST_PASSWORD
    assert verify_password(TEST_PASSWORD, created_user.password_hash)
    audit = session.query(AuditLog).filter(AuditLog.action == "USER_CREATED").one()
    assert audit.entity_id == str(created_user.id)
    assert audit.source == "WEB"
    assert set(PERMISSIONS_BY_ROLE) == set(ROLE_DESCRIPTIONS)
