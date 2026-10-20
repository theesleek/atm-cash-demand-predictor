from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.core.passwords import hash_password
from app.core.security import create_access_token
from app.models.atm import ATM, Alert, Forecast
from app.models.auth import Role, User
from app.services.alert_service import AlertNotFoundError, AlertService, AlertStateError
from app.services.notification_service import NotificationService


@pytest.fixture(autouse=True)
def mock_notifications(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(NotificationService, "notify", lambda *_args, **_kwargs: [])


@pytest.fixture
def alert_database() -> Iterator[tuple[Session, int, int]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    atm = ATM(
        atm_code="ATM-TEST",
        branch_id="BRANCH-TEST",
        region="TEST",
        status="active",
        capacity=10000.0,
        current_cash=5000.0,
        daily_demand=1000.0,
    )
    session.add(atm)
    session.commit()
    forecast = _create_forecast(session, atm.id)
    try:
        yield session, atm.id, forecast.id
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def alerts_api(
    alert_database: tuple[Session, int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    monkeypatch.setenv("JWT_SECRET_KEY", "phase-seven-alert-test-secret-value")
    session, _, _ = alert_database
    role = Role(name="BANK_MANAGER", description="test manager")
    session.add(role)
    session.commit()
    user = User(
        username="phase6-manager",
        password_hash=hash_password("phase6-manager-test-password"),
        role_id=role.id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    token = create_access_token(user.id, user.token_version)

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            client.headers["Authorization"] = f"Bearer {token}"
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _create_forecast(session: Session, atm_id: int, forecast_date: datetime | None = None) -> Forecast:
    forecast = Forecast(
        atm_id=atm_id,
        forecast_date=forecast_date or datetime(2026, 9, 30, tzinfo=timezone.utc),
        predicted_demand=1000.0,
        risk_level="WARNING",
        recommended_top_up=500.0,
        forecast_type="withdrawal_demand",
        model_version="test",
    )
    session.add(forecast)
    session.commit()
    session.refresh(forecast)
    return forecast


def test_normal_forecast_creates_no_alert(alert_database: tuple[Session, int, int]) -> None:
    session, atm_id, forecast_id = alert_database

    result = AlertService(session).create_or_update_risk_alert(
        atm_id=atm_id,
        atm_code="ATM-TEST",
        forecast_id=forecast_id,
        severity="NORMAL",
        projected_cash=5000.0,
    )

    assert result is None
    assert session.query(Alert).count() == 0


@pytest.mark.parametrize("severity", ["WARNING", "HIGH", "CRITICAL"])
def test_non_normal_forecast_creates_matching_alert(
    alert_database: tuple[Session, int, int],
    severity: str,
) -> None:
    session, atm_id, forecast_id = alert_database

    alert = AlertService(session).create_or_update_risk_alert(
        atm_id=atm_id,
        atm_code="ATM-TEST",
        forecast_id=forecast_id,
        severity=severity,
        projected_cash=100.0,
    )

    assert alert is not None
    assert alert.atm_id == atm_id
    assert alert.forecast_id == forecast_id
    assert alert.severity == severity
    assert alert.alert_type == "CASH_RISK"
    assert alert.status == "OPEN"
    assert alert.action_source == "SYSTEM"


def test_duplicate_active_condition_updates_existing_alert(alert_database: tuple[Session, int, int]) -> None:
    session, atm_id, first_forecast_id = alert_database
    service = AlertService(session)
    first_alert = service.create_or_update_risk_alert(
        atm_id, "ATM-TEST", first_forecast_id, "WARNING", 900.0
    )
    second_forecast = _create_forecast(session, atm_id, datetime(2026, 10, 1, tzinfo=timezone.utc))

    updated_alert = service.create_or_update_risk_alert(
        atm_id, "ATM-TEST", second_forecast.id, "WARNING", 700.0
    )

    assert first_alert is not None
    assert updated_alert is not None
    assert updated_alert.id == first_alert.id
    assert updated_alert.forecast_id == second_forecast.id
    assert updated_alert.message.endswith("700.00.")
    assert session.query(Alert).count() == 1


def test_active_alert_uniqueness_is_enforced_by_database(
    alert_database: tuple[Session, int, int],
) -> None:
    session, atm_id, forecast_id = alert_database
    first = AlertService(session).create_or_update_risk_alert(
        atm_id, "ATM-TEST", forecast_id, "HIGH", 400.0
    )
    assert first is not None
    duplicate = Alert(
        atm_id=atm_id,
        forecast_id=forecast_id,
        alert_type="CASH_RISK",
        severity="HIGH",
        status="OPEN",
        message="duplicate",
        action_source="SYSTEM",
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_acknowledge_and_resolve_record_actor_and_source(alert_database: tuple[Session, int, int]) -> None:
    session, atm_id, forecast_id = alert_database
    alert = AlertService(session).create_or_update_risk_alert(
        atm_id, "ATM-TEST", forecast_id, "HIGH", 400.0
    )
    assert alert is not None
    service = AlertService(session)

    acknowledged = service.acknowledge(alert.id, "operator-1", "WEB")
    resolved = service.resolve(alert.id, "operator-2", "API")

    assert acknowledged["status"] == "ACKNOWLEDGED"
    assert acknowledged["acknowledged_by"] == "operator-1"
    assert acknowledged["acknowledged_at"] is not None
    assert acknowledged["action_source"] == "WEB"
    assert resolved["status"] == "RESOLVED"
    assert resolved["resolved_by"] == "operator-2"
    assert resolved["resolved_at"] is not None
    assert resolved["action_source"] == "API"


def test_resolved_condition_creates_new_alert(alert_database: tuple[Session, int, int]) -> None:
    session, atm_id, forecast_id = alert_database
    service = AlertService(session)
    old_alert = service.create_or_update_risk_alert(
        atm_id, "ATM-TEST", forecast_id, "CRITICAL", 0.0
    )
    assert old_alert is not None
    service.resolve(old_alert.id, "operator", "WEB")

    next_forecast = _create_forecast(session, atm_id, datetime(2026, 10, 1, tzinfo=timezone.utc))
    new_alert = service.create_or_update_risk_alert(
        atm_id, "ATM-TEST", next_forecast.id, "CRITICAL", 0.0
    )

    assert new_alert is not None
    assert new_alert.id != old_alert.id
    assert session.query(Alert).count() == 2


def test_invalid_alert_and_transition_are_rejected(alert_database: tuple[Session, int, int]) -> None:
    session, atm_id, forecast_id = alert_database
    service = AlertService(session)

    with pytest.raises(AlertNotFoundError):
        service.get_alert(9999)

    alert = service.create_or_update_risk_alert(
        atm_id, "ATM-TEST", forecast_id, "WARNING", 300.0
    )
    assert alert is not None
    service.resolve(alert.id, "operator", "API")
    with pytest.raises(AlertStateError):
        service.acknowledge(alert.id, "operator", "API")


def test_alert_http_lifecycle(alerts_api: TestClient, alert_database: tuple[Session, int, int]) -> None:
    session, atm_id, forecast_id = alert_database
    alert = AlertService(session).create_or_update_risk_alert(
        atm_id, "ATM-TEST", forecast_id, "WARNING", 800.0
    )
    assert alert is not None

    listed = alerts_api.get("/alerts?atm_id=ATM-TEST&status=OPEN")
    detail = alerts_api.get(f"/alerts/{alert.id}")
    acknowledged = alerts_api.post(
        f"/alerts/{alert.id}/acknowledge",
        json={"source": "WEB"},
    )
    resolved = alerts_api.post(
        f"/alerts/{alert.id}/resolve",
        json={"source": "API"},
    )

    assert listed.status_code == 200
    assert listed.json()[0]["alert_id"] == alert.id
    assert detail.status_code == 200
    assert detail.json()["forecast_id"] == forecast_id
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "ACKNOWLEDGED"
    assert acknowledged.json()["acknowledged_by"] == "phase6-manager"
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"


def test_alert_http_invalid_id_returns_404(alerts_api: TestClient) -> None:
    response = alerts_api.get("/alerts/9999")

    assert response.status_code == 404
