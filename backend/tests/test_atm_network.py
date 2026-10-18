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
from app.data import tinkoff_history
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.atm import ATM, CashInventory, Forecast
from app.models.auth import Role, User
from app.models.ingestion import ATMHistoryRecord, Dataset, DatasetVersion
from app.models.replenishment import Replenishment


@pytest.fixture
def network_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Session, User, User, User, ATM, ATM]]:
    monkeypatch.setenv("JWT_SECRET_KEY", "phase-ten-network-api-test-secret-at-least-32-chars")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    roles = {
        name: Role(name=name, description=ROLE_DESCRIPTIONS[name])
        for name in ("BANK_MANAGER", "OPERATIONS_OFFICER", "ANALYST")
    }
    session.add_all(roles.values())
    session.commit()
    manager = User(username="network-manager", password_hash="test", role_id=roles["BANK_MANAGER"].id)
    officer = User(username="network-officer", password_hash="test", role_id=roles["OPERATIONS_OFFICER"].id)
    analyst = User(username="network-analyst", password_hash="test", role_id=roles["ANALYST"].id)
    atm_with_forecast = ATM(
        atm_code="ATM-NET-01",
        branch_id="BRANCH-NORTH",
        region="North",
        status="active",
        capacity=10000.0,
        current_cash=5000.0,
        daily_demand=1200.0,
    )
    atm_without_forecast = ATM(
        atm_code="ATM-NET-02",
        branch_id="BRANCH-SOUTH",
        region="South",
        status="maintenance",
        capacity=8000.0,
        current_cash=3000.0,
        daily_demand=800.0,
    )
    session.add_all([manager, officer, analyst, atm_with_forecast, atm_without_forecast])
    session.commit()
    for record in (manager, officer, analyst, atm_with_forecast, atm_without_forecast):
        session.refresh(record)

    forecast = Forecast(
        atm_id=atm_with_forecast.id,
        forecast_date=datetime(2026, 9, 30, tzinfo=timezone.utc),
        predicted_demand=1500.0,
        risk_level="HIGH",
        recommended_top_up=1000.0,
        model_version="test",
    )
    inventory = CashInventory(
        atm_id=atm_with_forecast.id,
        cash_on_hand=4200.0,
        capacity=10000.0,
        status="healthy",
    )
    session.add_all([forecast, inventory])
    session.commit()
    session.refresh(forecast)
    dataset = Dataset(name="synthetic-network-history", source="TEST")
    session.add(dataset)
    session.flush()
    version = DatasetVersion(
        dataset_id=dataset.id,
        version=1,
        source="TEST",
        uploaded_by=manager.id,
        status="INGESTED",
        rows_received=14,
        rows_accepted=14,
        atm_codes=[atm_with_forecast.atm_code],
    )
    session.add(version)
    session.flush()
    session.add_all(
        [
            ATMHistoryRecord(
                atm_id=atm_with_forecast.id,
                dataset_version_id=version.id,
                observed_at=datetime(2026, 9, 1 + offset, tzinfo=timezone.utc),
                operation_type="withdrawal",
                amount=100.0 + offset,
                record_fingerprint=f"synthetic-network-history-{offset}",
            )
            for offset in range(14)
        ]
    )
    session.commit()
    older = Replenishment(
        atm_id=atm_with_forecast.id,
        requested_amount=600.0,
        status="COMPLETED",
        requested_by=officer.id,
        created_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
    )
    newer = Replenishment(
        atm_id=atm_with_forecast.id,
        forecast_id=forecast.id,
        requested_amount=1000.0,
        status="REQUESTED",
        requested_by=manager.id,
        created_at=datetime(2026, 9, 29, tzinfo=timezone.utc),
    )
    session.add_all([older, newer])
    session.commit()
    manager_token = create_access_token(manager.id, manager.token_version)

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            client.headers["Authorization"] = f"Bearer {manager_token}"
            yield client, session, manager, officer, analyst, atm_with_forecast, atm_without_forecast
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_network_endpoint_returns_persisted_values_without_generating_forecasts(network_environment) -> None:
    client, session, _manager, _officer, _analyst, atm_with_forecast, atm_without_forecast = network_environment
    forecast_count = session.query(Forecast).count()

    response = client.get("/atms/network")

    assert response.status_code == 200
    rows = {row["atm_code"]: row for row in response.json()}
    assert len(rows) == 2
    assert rows[atm_with_forecast.atm_code]["location"] == "BRANCH-NORTH, North"
    assert rows[atm_with_forecast.atm_code]["current_cash"] == 4200.0
    assert rows[atm_with_forecast.atm_code]["predicted_demand"] == 1500.0
    assert rows[atm_with_forecast.atm_code]["projected_cash"] == 2700.0
    assert rows[atm_with_forecast.atm_code]["risk_level"] == "HIGH"
    assert rows[atm_with_forecast.atm_code]["last_replenishment_status"] == "REQUESTED"
    assert rows[atm_without_forecast.atm_code]["predicted_demand"] is None
    assert rows[atm_without_forecast.atm_code]["projected_cash"] is None
    assert session.query(Forecast).count() == forecast_count


def test_network_endpoint_scopes_replenishments_for_operations_officer(network_environment) -> None:
    client, _session, _manager, officer, _analyst, atm_with_forecast, _atm_without_forecast = network_environment
    token = create_access_token(officer.id, officer.token_version)

    response = client.get("/atms/network", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    rows = {row["atm_code"]: row for row in response.json()}
    assert rows[atm_with_forecast.atm_code]["last_replenishment_status"] == "COMPLETED"


def test_atm_intelligence_uses_shared_risk_logic_and_role_scoped_records(
    network_environment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _session, _manager, officer, analyst, atm, _other_atm = network_environment
    monkeypatch.setattr(tinkoff_history, "PROTOTYPE_ATM_ID_MAP", {atm.atm_code: 74})

    manager_data = client.get(f"/atms/{atm.atm_code}/intelligence").json()
    officer_data = client.get(
        f"/atms/{atm.atm_code}/intelligence",
        headers={"Authorization": f"Bearer {create_access_token(officer.id, officer.token_version)}"},
    ).json()
    analyst_data = client.get(
        f"/atms/{atm.atm_code}/intelligence",
        headers={"Authorization": f"Bearer {create_access_token(analyst.id, analyst.token_version)}"},
    ).json()

    assert manager_data["risk_level"] == "NORMAL"
    assert "warning threshold" in manager_data["risk_explanation"]
    assert manager_data["recommended_replenishment"] == 0.0
    assert len(manager_data["historical_demand"]) > 0
    assert manager_data["last_replenishment"]["status"] == "REQUESTED"
    assert officer_data["last_replenishment"]["status"] == "COMPLETED"
    assert analyst_data["last_replenishment"] is None


def test_persisted_forecast_endpoint_returns_linkable_forecast_values(network_environment) -> None:
    client, session, _manager, _officer, _analyst, atm, _other_atm = network_environment
    forecast = session.query(Forecast).filter(Forecast.atm_id == atm.id).one()
    forecast_count = session.query(Forecast).count()

    response = client.get(f"/forecasts/{forecast.id}")

    assert response.status_code == 200
    assert response.json()["forecast_id"] == forecast.id
    assert response.json()["atm_id"] == atm.atm_code
    assert response.json()["predicted_demand"] == forecast.predicted_demand
    assert response.json()["projected_cash"] == 2700.0
    assert response.json()["recommended_replenishment"] == forecast.recommended_top_up
    assert session.query(Forecast).count() == forecast_count
