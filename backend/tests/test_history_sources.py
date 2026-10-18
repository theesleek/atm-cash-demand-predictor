from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.ingestion import ATMHistoryRecord, Dataset, DatasetVersion
from app.services.data_quality_service import get_data_quality_report


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_data_quality_is_structured_unavailable_without_uploaded_history() -> None:
    session = _session()
    try:
        report = get_data_quality_report(session=session)
        assert report["status"] == "UNAVAILABLE"
        assert report["source"] == "uploaded_database"
        assert report["ingestion"] is None
    finally:
        session.close()


def test_data_quality_uses_uploaded_history_without_local_csv() -> None:
    session = _session()
    try:
        dataset = Dataset(name="focused-synthetic-history", source="TEST")
        session.add(dataset)
        session.flush()
        version = DatasetVersion(
            dataset_id=dataset.id,
            version=1,
            source="TEST",
            uploaded_by=1,
            status="INGESTED",
            rows_received=14,
            rows_accepted=14,
            atm_codes=["ATM-001"],
        )
        session.add(version)
        session.flush()
        session.add_all(
            [
                ATMHistoryRecord(
                    atm_id=1,
                    dataset_version_id=version.id,
                    observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=offset),
                    operation_type="withdrawal" if offset % 2 else "deposit",
                    amount=100.0 + offset,
                    record_fingerprint=f"focused-synthetic-history-{offset}",
                )
                for offset in range(14)
            ]
        )
        session.commit()

        report = get_data_quality_report(session=session)
        assert report["status"] == "GOOD"
        assert report["source"] == "uploaded_database"
        assert report["total_processed_rows"] == 14
        assert report["ingestion"]["dataset_version"] == "database:uploaded-history"
    finally:
        session.close()
