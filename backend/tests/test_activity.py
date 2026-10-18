from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.permissions import ROLE_DESCRIPTIONS
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.auth import AuditLog, Role, User


@pytest.fixture
def activity_api(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Session, dict[str, User]]]:
    monkeypatch.setenv("JWT_SECRET_KEY", "phase-fourteen-activity-test-secret-over-32-characters")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    role_names = ("SUPER_ADMIN", "BANK_MANAGER", "OPERATIONS_OFFICER", "ANALYST")
    roles = {name: Role(name=name, description=ROLE_DESCRIPTIONS[name]) for name in role_names}
    session.add_all(roles.values())
    session.commit()
    users = {
        name: User(username=f"activity-{name.lower()}", password_hash="test", role_id=roles[name].id)
        for name in role_names
    }
    session.add_all(users.values())
    session.commit()
    for user in users.values():
        session.refresh(user)

    session.add_all(
        [
            AuditLog(
                user_id=users["OPERATIONS_OFFICER"].id,
                action="ALERT_ACKNOWLEDGED",
                entity_type="ALERT",
                entity_id="12",
                source="WEB",
                metadata_json={},
                timestamp=datetime(2026, 10, 1, 9, tzinfo=timezone.utc),
            ),
            AuditLog(
                user_id=users["BANK_MANAGER"].id,
                action="REPLENISHMENT_APPROVED",
                entity_type="REPLENISHMENT",
                entity_id="22",
                source="WEB",
                metadata_json={},
                timestamp=datetime(2026, 10, 1, 10, tzinfo=timezone.utc),
            ),
            AuditLog(
                user_id=None,
                action="RISK_ALERT_UPSERTED",
                entity_type="ALERT",
                entity_id="13",
                source="SYSTEM",
                metadata_json={},
                timestamp=datetime(2026, 9, 30, 10, tzinfo=timezone.utc),
            ),
        ]
    )
    session.commit()
    tokens = {name: create_access_token(user.id, user.token_version) for name, user in users.items()}

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            client.headers["Authorization"] = f"Bearer {tokens['SUPER_ADMIN']}"
            yield client, session, users
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_activity_endpoint_returns_recent_audit_entries_and_filters(activity_api) -> None:
    client, _session, users = activity_api

    all_entries = client.get("/activity")
    filtered = client.get(
        "/activity",
        params={
            "user_id": users["OPERATIONS_OFFICER"].id,
            "action": "alert_acknowledged",
            "source": "WEB",
            "date_from": "2026-10-01",
            "date_to": "2026-10-01",
            "entity_type": "alert",
        },
    )

    assert all_entries.status_code == 200
    assert len(all_entries.json()) == 3
    assert all_entries.json()[0]["action"] == "REPLENISHMENT_APPROVED"
    assert all_entries.json()[0]["username"] == users["BANK_MANAGER"].username
    assert all_entries.json()[0]["source"] == "WEB"
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["entity_id"] == "12"
    assert filtered.json()[0]["action"] == "ALERT_ACKNOWLEDGED"


def test_activity_endpoint_requires_audit_permission(activity_api) -> None:
    client, _session, users = activity_api
    analyst = users["ANALYST"]
    token = create_access_token(analyst.id, analyst.token_version)

    response = client.get("/activity", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403