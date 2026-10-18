from __future__ import annotations

from datetime import datetime, timedelta, timezone
from collections.abc import Iterator

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
from app.models.atm import ATM
from app.models.auth import AuditLog, Role, User
from app.models.ingestion import ATMHistoryRecord, DatasetVersion
from app.services.ingestion_service import IngestionService


@pytest.fixture
def import_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Session, User, User, ATM]]:
    monkeypatch.setenv("JWT_SECRET_KEY", "phase-25-ingestion-test-secret-at-least-32-chars")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    roles = {name: Role(name=name, description=ROLE_DESCRIPTIONS[name]) for name in ("SUPER_ADMIN", "ANALYST", "VIEWER")}
    session.add_all(roles.values())
    session.commit()
    admin = User(username="phase25-admin", password_hash="test", role_id=roles["SUPER_ADMIN"].id)
    analyst = User(username="phase25-analyst", password_hash="test", role_id=roles["ANALYST"].id)
    viewer = User(username="phase25-viewer", password_hash="test", role_id=roles["VIEWER"].id)
    atm = ATM(atm_code="ATM-025", branch_id="BR-025", region="North", capacity=10000, current_cash=7000, daily_demand=500, status="PENDING")
    session.add_all([admin, analyst, viewer, atm])
    session.commit()
    for record in (admin, analyst, viewer, atm):
        session.refresh(record)

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client, session, admin, analyst, atm
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _token(user: User) -> str:
    return create_access_token(user.id, user.token_version)


def _headers(user: User, *, web: bool = False) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {_token(user)}"}
    if web:
        headers["X-Action-Source"] = "WEB"
    return headers


def test_atm_creation_and_duplicate_are_server_guarded(import_environment) -> None:
    client, _session, admin, analyst, _atm = import_environment
    payload = {"atm_code": "ATM-026", "branch_id": "BR-026", "region": "West", "capacity": 12000, "status": "PENDING"}
    created = client.post("/atms", json=payload, headers=_headers(admin, web=True))
    assert created.status_code == 201
    assert created.json()["status"] == "PENDING"
    assert client.post("/atms", json=payload, headers=_headers(admin, web=True)).status_code == 409
    assert client.post("/atms", json={**payload, "atm_code": "ATM-027"}, headers=_headers(analyst, web=True)).status_code == 403
    activated = client.patch("/atms/ATM-026", json={"status": "ACTIVE"}, headers=_headers(admin, web=True))
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"
    assert client.patch("/atms/ATM-026", json={"status": "INACTIVE"}, headers=_headers(analyst, web=True)).status_code == 403
    deactivated = client.patch("/atms/ATM-026", json={"status": "INACTIVE"}, headers=_headers(admin, web=True))
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "INACTIVE"


def test_csv_validation_reports_errors_without_ingesting(import_environment) -> None:
    client, session, admin, analyst, atm = import_environment
    csv = "atm_id,datetime,operation_type,amount\nATM-025,2026-01-01T10:00:00Z,withdrawal,100\nUNKNOWN,not-a-date,withdrawal,-2\nATM-025,2026-01-01T10:00:00Z,withdrawal,100\n"
    response = client.post("/data-imports/validate", files={"file": ("history.csv", csv, "text/csv")}, headers=_headers(analyst, web=True))
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "VALIDATED"
    assert body["rows_accepted"] == 1
    assert body["rows_rejected"] == 2
    assert {reason for row in body["validation_report"]["rejected_rows"] for reason in row["reasons"]} >= {"UNKNOWN_ATM", "INVALID_DATETIME", "INVALID_AMOUNT", "DUPLICATE_RECORD"}
    assert session.query(ATMHistoryRecord).count() == 0
    assert client.post(f"/data-imports/{body['dataset_version_id']}/approve", headers=_headers(analyst, web=True)).status_code == 403


def test_missing_required_columns_are_rejected_without_records(import_environment) -> None:
    client, session, _admin, analyst, _atm = import_environment
    response = client.post(
        "/data-imports/validate",
        files={"file": ("missing-columns.csv", "atm_id,amount\nATM-025,100\n", "text/csv")},
        headers=_headers(analyst, web=True),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "REJECTED"
    assert body["rows_accepted"] == 0
    assert body["rows_rejected"] == 1
    assert body["validation_report"]["schema_errors"] == ["MISSING_REQUIRED_FIELD"]
    assert set(body["validation_report"]["rejected_rows"][0]["missing_columns"]) == {"datetime", "operation_type"}
    assert session.query(ATMHistoryRecord).count() == 0


def test_upload_and_listing_require_data_permission(import_environment) -> None:
    client, session, _admin, _analyst, _atm = import_environment
    viewer = session.query(User).filter(User.username == "phase25-viewer").one()

    assert client.post(
        "/data-imports/validate",
        files={"file": ("history.csv", "atm_id,datetime,operation_type,amount\n", "text/csv")},
        headers=_headers(viewer),
    ).status_code == 403
    assert client.get("/data-imports", headers=_headers(viewer)).status_code == 403


def test_dataset_approval_ingestion_and_readiness(import_environment, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session, admin, _analyst, atm = import_environment
    monkeypatch.setattr(tinkoff_history, "PROTOTYPE_ATM_ID_MAP", {atm.atm_code: 74})
    start = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    rows = [f"{atm.atm_code},{(start + timedelta(days=index)).isoformat()},withdrawal,{100 + index}" for index in range(14)]
    csv = "atm_id,datetime,operation_type,amount\n" + "\n".join(rows) + "\n"
    uploaded = client.post("/data-imports/validate", files={"file": ("history.csv", csv, "text/csv")}, headers=_headers(admin, web=True)).json()
    assert uploaded["status"] == "VALIDATED"
    approved = client.post(f"/data-imports/{uploaded['dataset_version_id']}/approve", headers=_headers(admin, web=True))
    assert approved.status_code == 200
    ingested = client.post(f"/data-imports/{uploaded['dataset_version_id']}/ingest", headers=_headers(admin, web=True))
    assert ingested.status_code == 200
    assert ingested.json()["status"] == "INGESTED"
    assert session.query(ATMHistoryRecord).count() == 14
    readiness = client.get(f"/atms/{atm.atm_code}/readiness", headers=_headers(admin)).json()
    assert readiness["status"] == "READY"
    assert readiness["history_days"] == 14
    forecast = client.get(f"/forecast?atm_id={atm.atm_code}", headers=_headers(admin))
    assert forecast.status_code == 200
    assert forecast.json()["forecast_source"] == "uploaded_dataset"
    assert client.post(f"/data-imports/{uploaded['dataset_version_id']}/ingest", headers=_headers(admin, web=True)).status_code == 409

    repeated = client.post(
        "/data-imports/validate",
        files={"file": ("repeated.csv", csv, "text/csv")},
        headers=_headers(admin, web=True),
    )
    assert repeated.status_code == 201
    assert repeated.json()["status"] == "REJECTED"
    assert repeated.json()["rows_accepted"] == 0
    assert repeated.json()["duplicate_rows"] == 14
    assert session.query(ATMHistoryRecord).count() == 14
    assert {entry.action for entry in session.query(AuditLog).all()} >= {"DATASET_VALIDATED", "DATASET_APPROVED", "DATASET_INGESTED"}


def test_ingestion_rolls_back_history_and_status_on_commit_failure(import_environment, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session, admin, _analyst, atm = import_environment
    start = datetime(2026, 2, 1, 10, tzinfo=timezone.utc)
    rows = [f"{atm.atm_code},{(start + timedelta(days=index)).isoformat()},withdrawal,{200 + index}" for index in range(2)]
    csv = "atm_id,datetime,operation_type,amount\n" + "\n".join(rows) + "\n"
    uploaded = client.post("/data-imports/validate", files={"file": ("rollback.csv", csv, "text/csv")}, headers=_headers(admin, web=True)).json()
    assert client.post(f"/data-imports/{uploaded['dataset_version_id']}/approve", headers=_headers(admin, web=True)).status_code == 200

    def fail_commit() -> None:
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="simulated commit failure"):
        IngestionService(session).ingest(uploaded["dataset_version_id"], admin.id)

    session.expire_all()
    version = session.get(DatasetVersion, uploaded["dataset_version_id"])
    assert version is not None
    assert version.status == "APPROVED"
    assert session.query(ATMHistoryRecord).count() == 0


def test_new_atm_is_insufficient_until_history_exists(import_environment) -> None:
    client, _session, admin, _analyst, atm = import_environment
    readiness = client.get(f"/atms/{atm.atm_code}/readiness", headers=_headers(admin)).json()
    assert readiness["status"] == "INSUFFICIENT_HISTORY"
    forecast = client.get(f"/forecast?atm_id={atm.atm_code}", headers=_headers(admin))
    assert forecast.status_code == 422
    assert "Insufficient" in forecast.json()["detail"]
