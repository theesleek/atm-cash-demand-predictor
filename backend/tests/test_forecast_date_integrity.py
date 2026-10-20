from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.atm import ATM, Forecast
from app.repositories.forecast_repository import ForecastRepository


MIGRATION_PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0008_forecast_date_required.py"
SPEC = importlib.util.spec_from_file_location("forecast_date_required_migration", MIGRATION_PATH)
assert SPEC is not None and SPEC.loader is not None
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


def _session() -> Session:
    engine = create_engine("sqlite://")
    from app.models import ingestion, model_registry, notification, operations, replenishment  # noqa: F401

    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    session.add(ATM(atm_code="ATM-DATE", branch_id="BR-DATE", region="North"))
    session.commit()
    return session


def _forecast(atm_id: int, forecast_date: datetime | None, model_version: str = "test") -> Forecast:
    return Forecast(
        atm_id=atm_id,
        forecast_date=forecast_date,
        predicted_demand=100.0,
        risk_level="WARNING",
        recommended_top_up=50.0,
        forecast_type="withdrawal_demand",
        model_version=model_version,
    )


def test_repository_rejects_null_forecast_date() -> None:
    session = _session()
    try:
        with pytest.raises(ValueError, match="forecast_date is required"):
            ForecastRepository(session).get_or_create(
                1, 100.0, "WARNING", 50.0, None, "test", forecast_type="withdrawal_demand"
            )  # type: ignore[arg-type]
    finally:
        session.close()


def test_database_rejects_null_and_accepts_dated_forecast() -> None:
    session = _session()
    try:
        session.add(_forecast(1, None))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        dated = _forecast(1, datetime(2026, 10, 20, tzinfo=timezone.utc))
        session.add(dated)
        session.commit()
        assert dated.id is not None
    finally:
        session.close()


def test_uniqueness_constraint_still_rejects_duplicate_dated_identity() -> None:
    session = _session()
    try:
        forecast_date = datetime(2026, 10, 20, tzinfo=timezone.utc)
        session.add(_forecast(1, forecast_date))
        session.commit()
        session.add(_forecast(1, forecast_date))
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.close()


class _Result:
    def __init__(self, count: int):
        self.count = count

    def scalar_one(self) -> int:
        return self.count


class _Bind:
    def __init__(self, count: int):
        self.count = count
        self.dialect = type("Dialect", (), {"name": "postgresql"})()

    def execute(self, _statement):
        return _Result(self.count)


class _Operations:
    def __init__(self, count: int):
        self.bind = _Bind(count)
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def get_bind(self):
        return self.bind

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))

        return record


def test_migration_aborts_on_existing_null_rows_without_altering_schema(monkeypatch) -> None:
    operations = _Operations(2)
    monkeypatch.setattr(migration, "op", operations)

    with pytest.raises(RuntimeError, match=r"2 existing forecast row\(s\)"):
        migration.upgrade()

    assert operations.calls == []


def test_migration_alters_forecast_date_only_after_null_preflight(monkeypatch) -> None:
    operations = _Operations(0)
    monkeypatch.setattr(migration, "op", operations)

    migration.upgrade()

    assert [name for name, _args, _kwargs in operations.calls] == ["alter_column"]
    assert operations.calls[0][1][0:2] == ("forecasts", "forecast_date")
    assert operations.calls[0][2]["nullable"] is False
