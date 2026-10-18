from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite:///./test_atm_cash.db"
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret-key-for-phase-seven")

from fastapi.testclient import TestClient

from app.core.passwords import hash_password
from app.core.security import create_access_token
from app.db.session import SessionLocal, create_db_and_tables, seed_security_data
from app.main import app
from app.models.auth import Role, User
from app.models.ingestion import ATMHistoryRecord
from app.services.data_quality_service import get_data_quality_report
from app.services.model_registry_service import get_model_metadata
from app.services.model_evaluation_service import get_model_evaluation


client = TestClient(app)


def _auth_headers() -> dict[str, str]:
    create_db_and_tables()
    db = SessionLocal()
    try:
        seed_security_data(db)
        role = db.query(Role).filter(Role.name == "SUPER_ADMIN").one()
        user = db.query(User).filter(User.username == "analytics-tests-admin").first()
        if user is None:
            user = User(username="analytics-tests-admin", password_hash=hash_password("analytics-tests-password"), role_id=role.id)
            db.add(user)
            db.commit()
            db.refresh(user)
        return {"Authorization": f"Bearer {create_access_token(user.id, user.token_version)}"}
    finally:
        db.close()


def _clear_uploaded_history() -> None:
    db = SessionLocal()
    try:
        db.query(ATMHistoryRecord).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_data_quality_report_uses_explicit_local_fixture(synthetic_processed_history) -> None:
    report = get_data_quality_report(history_path=synthetic_processed_history)
    assert report["total_processed_rows"] == 600
    assert report["expected_atm_days"] == 600
    assert report["observed_atm_days"] == 600
    assert report["unobserved_atm_days"] == 0
    assert report["internally_imputed_observations"] == 2
    assert report["pre_imputation_observed_atm_days"] == 598
    assert report["pre_imputation_unobserved_atm_days"] == 2
    assert report["actual_atm_days"] == report["observed_atm_days"]
    assert report["missing_atm_days"] == report["unobserved_atm_days"]
    assert report["status"] in {"GOOD", "ATTENTION"}
    assert report["ingestion"]["rows_received"] >= report["ingestion"]["rows_accepted"]
    assert report["ingestion"]["dataset_version"].startswith("sha256:")


def test_model_metadata_exposes_active_artifact_identity(synthetic_processed_history) -> None:
    metadata = get_model_metadata(history_path=synthetic_processed_history)
    assert metadata["model_name"] == "linear_regression+random_forest"
    assert metadata["status"] == "ACTIVE"
    assert metadata["evaluation_sample_count"] > 0
    assert all(item["checksum"].startswith("sha256:") for item in metadata["artifacts"])


def test_model_evaluation_reports_all_requested_models(synthetic_processed_history) -> None:
    report = get_model_evaluation(history_path=synthetic_processed_history)
    assert [row["model"] for row in report["models"]] == [
        "7_day_average",
        "linear_regression",
        "random_forest",
        "xgboost",
        "lightgbm",
        "ensemble",
    ]
    assert all(row["status"] == "available" for row in report["models"])
    assert all(row["r2"] is not None for row in report["models"])
    assert all(row["sample_count"] > 0 for row in report["models"])


def test_analytics_endpoints_require_authorization() -> None:
    assert client.get("/data-quality").status_code == 401
    assert client.get("/forecast/evaluation").status_code == 401


def test_data_quality_endpoint_reports_unavailable_without_uploaded_history() -> None:
    _clear_uploaded_history()
    response = client.get("/data-quality", headers=_auth_headers())
    assert response.status_code == 200
    assert response.json()["status"] == "UNAVAILABLE"
    assert response.json()["source"] == "uploaded_database"


def test_forecast_evaluation_endpoint_reports_unavailable_without_uploaded_history() -> None:
    _clear_uploaded_history()
    response = client.get("/forecast/evaluation", headers=_auth_headers())
    assert response.status_code == 200
    assert response.json()["status"] == "UNAVAILABLE"
    assert response.json()["data_source"] == "uploaded_database"
