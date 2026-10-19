import os
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

os.environ["DATABASE_URL"] = "sqlite:///./test_atm_cash.db"
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret-key-for-phase-seven")

from fastapi.testclient import TestClient

from app.db.session import SessionLocal, create_db_and_tables, seed_atm_data, seed_security_data
from app.core.passwords import hash_password
from app.core.security import create_access_token
from app.main import app
from app.ml import inference
from app.ml.model_loader import ModelArtifactCompatibilityError, ModelBundle
from app.models.atm import ATM, Alert, Forecast
from app.models.auth import Role, User
from app.models.ingestion import ATMHistoryRecord, Dataset, DatasetVersion

client = TestClient(app)


def _auth_headers() -> dict[str, str]:
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == "SUPER_ADMIN").one()
        user = db.query(User).filter(User.username == "phase-tests-admin").first()
        if user is None:
            user = User(
                username="phase-tests-admin",
                password_hash=hash_password("phase-tests-password"),
                role_id=role.id,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        token = create_access_token(user.id, user.token_version)
        return {"Authorization": f"Bearer {token}"}
    finally:
        db.close()


def _seed_uploaded_forecast_history() -> None:
    create_db_and_tables()
    db = SessionLocal()
    try:
        seed_atm_data(db)
        seed_security_data(db)
        atm = db.query(ATM).filter(ATM.atm_code == "ATM-001").one()
        if db.query(ATMHistoryRecord).filter(ATMHistoryRecord.atm_id == atm.id).count() >= 14:
            return
        user = db.query(User).filter(User.username == "phase-tests-admin").one()
        dataset = Dataset(name="synthetic-health-history", source="TEST")
        db.add(dataset)
        db.flush()
        version = DatasetVersion(
            dataset_id=dataset.id,
            version=1,
            source="TEST",
            uploaded_by=user.id,
            status="INGESTED",
            rows_received=14,
            rows_accepted=14,
            atm_codes=["ATM-001"],
        )
        db.add(version)
        db.flush()
        for offset in range(14):
            db.add(
                ATMHistoryRecord(
                    atm_id=atm.id,
                    dataset_version_id=version.id,
                    observed_at=datetime(2018, 9, 17 + offset, tzinfo=timezone.utc),
                    operation_type="withdrawal",
                    amount=100.0 + offset,
                    record_fingerprint=f"phase-health-history-{offset}",
                )
            )
        db.commit()
    finally:
        db.close()


def test_database_seeded() -> None:
    create_db_and_tables()
    db = SessionLocal()
    try:
        seed_atm_data(db)
        seed_security_data(db)
        assert db.query(ATM).count() >= 1
    finally:
        db.close()


def test_root_endpoint() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "ATM Cash Intelligence API is running." in response.json()["message"]


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_endpoint_checks_database() -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_atm_list_endpoint() -> None:
    response = client.get("/atms", headers=_auth_headers())
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) >= 1
    assert payload[0]["atm_code"]


def test_forecast_endpoint_uses_database_data(monkeypatch) -> None:
    config_path = Path(__file__).resolve().parents[2] / "backend" / "app" / "ml" / "artifacts" / "model_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    linear_model = Mock()
    linear_model.predict.return_value = [20000.0]
    random_forest_model = Mock()
    random_forest_model.predict.return_value = [30000.0]
    bundle = ModelBundle(
        models={"linear_regression": linear_model, "random_forest": random_forest_model},
        config=config,
    )
    monkeypatch.setattr(inference, "load_model_bundle", lambda: bundle)

    headers = _auth_headers()
    _seed_uploaded_forecast_history()
    response = client.get("/forecast?atm_id=ATM-001", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["atm_id"] == "ATM-001"
    assert payload["predicted_signed_net_cash_flow"] == 25000.0
    assert payload["predicted_demand"] is None
    assert payload["risk_level"] is None
    assert payload["risk_evaluation_status"] == "UNAVAILABLE"
    assert payload["risk_evaluation_reason"]
    assert payload["target"] == "next_day_cash_flow"
    assert payload["forecast_date"] == "2018-10-01"
    assert payload["model_name"] == "linear_regression+random_forest"
    assert payload["forecast_source"] == "uploaded_dataset"
    assert payload["inventory_source"] == "atm_record_fallback"
    assert payload["model_version"] == "phase4-production-50-50"
    assert payload["projected_cash"] is None
    assert payload["recommended_top_up"] is None
    assert payload["warning_threshold"] is None
    assert payload["high_threshold"] is None
    assert payload["critical_threshold"] is None

    db = SessionLocal()
    try:
        latest_forecast = (
            db.query(Forecast)
            .filter(Forecast.atm_id == 1)
            .order_by(Forecast.id.desc())
            .first()
        )
        assert latest_forecast is not None
        assert latest_forecast.predicted_signed_net_cash_flow == 25000.0
        assert latest_forecast.predicted_demand is None
        assert latest_forecast.risk_level is None
        assert latest_forecast.risk_evaluation_status == "UNAVAILABLE"
        assert db.query(Alert).filter(Alert.atm_id == 1, Alert.forecast_id == latest_forecast.id).count() == 0
    finally:
        db.close()


def test_forecast_endpoint_reports_model_compatibility_error(monkeypatch) -> None:
    monkeypatch.setattr(
        inference,
        "load_model_bundle",
        lambda: (_ for _ in ()).throw(
            ModelArtifactCompatibilityError("Model artifacts require scikit-learn 1.6.1.")
        ),
    )

    headers = _auth_headers()
    _seed_uploaded_forecast_history()
    response = client.get("/forecast?atm_id=ATM-001", headers=headers)

    assert response.status_code == 503
    assert "scikit-learn 1.6.1" in response.json()["detail"]


def test_dashboard_summary_endpoint() -> None:
    response = client.get("/dashboard/summary", headers=_auth_headers())
    assert response.status_code == 200
    payload = response.json()
    assert "atms_monitored" in payload
    assert "critical_alerts" in payload
    assert payload["atms_monitored"] >= 1
