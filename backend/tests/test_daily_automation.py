from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import hashlib

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import config as config_module
from app.db.base import Base
from app.jobs import queue as queue_module
from app.jobs import worker as worker_module
from app.models.atm import ATM, Forecast
from app.models.auth import Role, User
from app.models.ingestion import ATMHistoryRecord, Dataset, DatasetVersion
from app.models.notification import NotificationDelivery
from app.models.operations import BackgroundJob, NotificationOutbox
from app.repositories.notification_repository import NotificationRepository
from app.services.daily_automation_service import DailyAutomationService
from app.services.forecast_service import ForecastResult
from app.services.notification_service import NotificationService


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'daily-automation.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_ready_atm(session, *, latest_date: date = date(2018, 1, 20)) -> ATM:
    role = Role(name="BANK_MANAGER", description="test")
    user = User(username="daily-test", password_hash="hash", role=role)
    atm = ATM(atm_code="ATM-001", branch_id="BR-1", region="R-1", capacity=1000, current_cash=800, daily_demand=100)
    dataset = Dataset(name="daily-test.csv", source="CSV")
    version = DatasetVersion(
        dataset=dataset,
        version=1,
        source="CSV",
        uploaded_by=user.id if user.id else 1,
        status="INGESTED",
        rows_received=14,
        rows_accepted=14,
        atm_codes=[atm.atm_code],
        date_from=latest_date - timedelta(days=13),
        date_to=latest_date,
        ingested_at=datetime.now(timezone.utc),
    )
    session.add_all([role, user, atm, dataset, version])
    session.flush()
    for offset in range(14):
        observed_at = datetime.combine(latest_date - timedelta(days=13 - offset), datetime.min.time(), tzinfo=timezone.utc)
        session.add(
            ATMHistoryRecord(
                atm_id=atm.id,
                dataset_version_id=version.id,
                observed_at=observed_at,
                operation_type="deposit",
                amount=100 + offset,
                record_fingerprint=f"daily-{offset}",
            )
        )
    session.commit()
    return atm


def _fake_forecast(*_args, **_kwargs):
    class FakeForecastService:
        def __init__(self, **_kwargs):
            pass

        def generate_forecast(self, atm_id, **_kwargs):
            return ForecastResult(
                atm_id=atm_id,
                predicted_demand=None,
                predicted_signed_net_cash_flow=123.0,
                risk_level=None,
                recommended_top_up=None,
                current_cash=800.0,
                capacity=1000.0,
                forecast_date="2018-01-21T00:00:00+00:00",
                target="next_day_cash_flow",
                model_name="test-model",
                model_version="test-model-v1",
                projected_cash=None,
                warning_threshold=None,
                high_threshold=None,
                critical_threshold=None,
                safety_buffer=None,
                risk_evaluation_status="UNAVAILABLE",
                risk_evaluation_reason="verified demand unavailable",
                source="uploaded_dataset",
            )

    return FakeForecastService


def test_daily_enqueue_is_disabled_by_default(tmp_path, monkeypatch):
    session = _session(tmp_path)
    disabled = replace(config_module.settings, daily_automation_enabled=False)
    monkeypatch.setattr(queue_module, "settings", disabled)
    assert queue_module.enqueue_daily_forecast_job(session, date(2018, 1, 20)) is None
    session.close()


def test_daily_enqueue_is_deduplicated_for_multiple_instances(tmp_path, monkeypatch):
    session = _session(tmp_path)
    enabled = replace(config_module.settings, daily_automation_enabled=True)
    monkeypatch.setattr(queue_module, "settings", enabled)
    first = queue_module.enqueue_daily_forecast_job(session, date(2018, 1, 20))
    second = queue_module.enqueue_daily_forecast_job(session, date(2018, 1, 20))
    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert session.query(queue_module.BackgroundJob).count() == 1
    session.close()


def test_worker_daily_scheduler_gates_polling_restarts_and_date_rollover(tmp_path, monkeypatch):
    session = _session(tmp_path)
    enabled = replace(config_module.settings, daily_automation_enabled=True)
    monkeypatch.setattr(queue_module, "settings", enabled)
    from app.jobs import worker as worker_module

    monkeypatch.setattr(worker_module, "settings", enabled)
    current = {"now": datetime(2018, 1, 20, 23, 59, tzinfo=timezone.utc)}
    factory = lambda: session
    first = worker_module.DailyJobScheduler(factory, lambda: current["now"])
    second = worker_module.DailyJobScheduler(factory, lambda: current["now"])

    assert first.tick() is True
    assert first.tick() is False
    assert second.tick() is True
    assert session.query(queue_module.BackgroundJob).count() == 1

    current["now"] = datetime(2018, 1, 21, 0, 1, tzinfo=timezone.utc)
    assert first.tick() is True
    assert session.query(queue_module.BackgroundJob).count() == 2
    session.close()


def test_worker_daily_scheduler_stays_disabled(tmp_path, monkeypatch):
    session = _session(tmp_path)
    disabled = replace(config_module.settings, daily_automation_enabled=False)
    monkeypatch.setattr(queue_module, "settings", disabled)
    from app.jobs import worker as worker_module

    monkeypatch.setattr(worker_module, "settings", disabled)
    scheduler = worker_module.DailyJobScheduler(lambda: session, lambda: datetime(2018, 1, 20, tzinfo=timezone.utc))
    assert scheduler.tick() is False
    assert session.query(queue_module.BackgroundJob).count() == 0
    session.close()


def test_worker_daily_scheduler_backs_off_after_enqueue_failure_and_recovers(tmp_path, monkeypatch):
    session = _session(tmp_path)
    enabled = replace(config_module.settings, daily_automation_enabled=True)
    monkeypatch.setattr(queue_module, "settings", enabled)
    monkeypatch.setattr(worker_module, "settings", enabled)
    current = {"now": datetime(2018, 1, 20, 0, 0, tzinfo=timezone.utc)}
    calls = {"count": 0}
    real_enqueue = worker_module.enqueue_daily_forecast_job

    def flaky_enqueue(current_session, operational_date):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary database outage")
        return real_enqueue(current_session, operational_date)

    monkeypatch.setattr(worker_module, "enqueue_daily_forecast_job", flaky_enqueue)
    scheduler = worker_module.DailyJobScheduler(
        lambda: session,
        lambda: current["now"],
        retry_backoff_seconds=30,
    )

    assert scheduler.tick() is False
    current["now"] += timedelta(seconds=10)
    assert scheduler.tick() is False
    assert calls["count"] == 1
    current["now"] += timedelta(seconds=20)
    assert scheduler.tick() is True
    assert calls["count"] == 2
    assert scheduler.tick() is False
    assert session.query(BackgroundJob).count() == 1
    current["now"] = datetime(2018, 1, 21, 0, 1, tzinfo=timezone.utc)
    assert scheduler.tick() is True
    assert session.query(BackgroundJob).count() == 2
    session.close()


def test_daily_run_skips_stale_history(tmp_path, monkeypatch):
    session = _session(tmp_path)
    _seed_ready_atm(session)
    settings = replace(config_module.settings, daily_automation_max_data_age_days=2)
    monkeypatch.setattr("app.services.daily_automation_service.settings", settings)
    result = DailyAutomationService(session).run({"operational_date": "2018-01-30"})
    assert result["run_status"] == "COMPLETED_WITH_SKIPS"
    assert result["eligible_atms"] == 0
    assert result["skipped_atms"][0]["reason"].startswith("Actual data is stale")
    assert session.query(Forecast).count() == 0
    session.close()


def test_daily_retry_does_not_duplicate_forecasts(tmp_path, monkeypatch):
    session = _session(tmp_path)
    _seed_ready_atm(session)
    settings = replace(config_module.settings, daily_automation_max_data_age_days=2)
    monkeypatch.setattr("app.services.daily_automation_service.settings", settings)
    monkeypatch.setattr("app.services.atm_service.ForecastService", _fake_forecast())
    payload = {"operational_date": "2018-01-20"}
    first = DailyAutomationService(session).run(payload)
    second = DailyAutomationService(session).run(payload)
    assert first["forecasts_created"] == 1
    assert second["forecasts_created"] == 0
    assert session.query(Forecast).count() == 1
    assert first["notification_status"] == "not_applicable"
    session.close()


def _delivery_key(event_key: str, channel: str, recipient: str = "") -> str:
    return hashlib.sha256(f"{event_key}|{channel}|{recipient}".encode("utf-8")).hexdigest()


def test_notification_status_reports_successful_persisted_delivery(tmp_path):
    session = _session(tmp_path)
    event_key = "RISK_HIGH:1"
    session.add_all([
        NotificationDelivery(
            event_type="RISK_HIGH",
            channel="TELEGRAM",
            recipient="",
            status="SENT",
            idempotency_key=_delivery_key(event_key, "TELEGRAM"),
        ),
        NotificationDelivery(
            event_type="RISK_HIGH",
            channel="EMAIL",
            recipient="",
            status="SENT",
            idempotency_key=_delivery_key(event_key, "EMAIL"),
        ),
    ])
    session.commit()
    assert NotificationService(session).notification_status("RISK_HIGH", event_key)["status"] == "sent"
    session.close()


def test_notification_status_reports_pending_outbox(tmp_path):
    session = _session(tmp_path)
    session.add(NotificationOutbox(event_key="RISK_HIGH:2", event_type="RISK_HIGH", subject="subject", message="message", status="PENDING"))
    session.commit()
    assert NotificationService(session).notification_status("RISK_HIGH", "RISK_HIGH:2")["status"] == "pending"
    session.close()


def test_notification_status_reports_failed_delivery(tmp_path):
    session = _session(tmp_path)
    event_key = "RISK_CRITICAL:3"
    session.add(NotificationDelivery(
        event_type="RISK_CRITICAL",
        channel="TELEGRAM",
        recipient="",
        status="FAILED",
        error="RuntimeError",
        idempotency_key=_delivery_key(event_key, "TELEGRAM"),
    ))
    session.commit()
    assert NotificationService(session).notification_status("RISK_CRITICAL", event_key)["status"] == "failed"
    session.close()


def test_daily_status_distinguishes_forecast_success_from_notification_failure(tmp_path, monkeypatch):
    session = _session(tmp_path)
    _seed_ready_atm(session)

    class FakeIngestion:
        @staticmethod
        def readiness(_atm):
            return {"status": "READY", "date_to": "2018-01-20"}

    class FakeATMService:
        def __init__(self, _session):
            self.ingestion_service = FakeIngestion()

        @staticmethod
        def get_forecast(_atm_code):
            return {
                "forecast_created": True,
                "forecast_date": "2018-01-21T00:00:00+00:00",
                "notification": {
                    "status": "failed",
                    "event_type": "RISK_HIGH",
                    "event_key": "RISK_HIGH:failure",
                },
            }

    monkeypatch.setattr("app.services.daily_automation_service.ATMService", FakeATMService)
    result = DailyAutomationService(session).run({"operational_date": "2018-01-20"})
    assert result["forecasts_created"] == 1
    assert result["notification_status"] == "failed"
    assert result["notification_failures"]
    assert result["run_status"] == "COMPLETED_WITH_ERRORS"
    session.close()


def test_daily_status_reports_no_eligible_notification(tmp_path, monkeypatch):
    session = _session(tmp_path)
    _seed_ready_atm(session)
    settings = replace(config_module.settings, daily_automation_max_data_age_days=2)
    monkeypatch.setattr("app.services.daily_automation_service.settings", settings)
    result = DailyAutomationService(session).run({"operational_date": "2018-01-30"})
    assert result["notification_status"] == "not_applicable"
    assert result["notification_outcomes"] == []
    session.close()


def test_status_refreshes_notification_state_from_persisted_outbox(tmp_path, monkeypatch):
    session = _session(tmp_path)
    session.add(NotificationOutbox(event_key="RISK_HIGH:refresh", event_type="RISK_HIGH", subject="subject", message="message", status="PENDING"))
    session.add(BackgroundJob(
        job_type="daily.forecast_refresh",
        dedupe_key="daily-forecast:2018-01-20",
        payload={
            "operational_date": "2018-01-20",
            "run_status": "COMPLETED",
            "notification_status": "sent",
            "notification_events": [{"atm_id": "ATM-001", "event_type": "RISK_HIGH", "event_key": "RISK_HIGH:refresh"}],
        },
    ))
    session.commit()
    monkeypatch.setattr("app.services.daily_automation_service.settings", replace(config_module.settings, daily_automation_enabled=True))
    status = DailyAutomationService.status(session)
    assert status["notification_status"] == "pending"
    assert status["last_job"]["notification_status"] == "pending"
    session.close()


def test_worker_crash_recovery_does_not_duplicate_forecasts(tmp_path, monkeypatch):
    session = _session(tmp_path)
    _seed_ready_atm(session)
    enabled = replace(config_module.settings, daily_automation_enabled=True, daily_automation_max_data_age_days=2)
    monkeypatch.setattr(queue_module, "settings", enabled)
    monkeypatch.setattr("app.services.daily_automation_service.settings", enabled)
    monkeypatch.setattr("app.services.atm_service.ForecastService", _fake_forecast())
    job = queue_module.enqueue_daily_forecast_job(session, date(2018, 1, 20))
    assert job is not None

    from app.jobs import worker as worker_module

    real_service = DailyAutomationService
    calls = {"count": 0}

    class CrashAfterCommitService:
        def __init__(self, current_session):
            self.current_session = current_session

        def run(self, payload):
            result = real_service(self.current_session).run(payload)
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("simulated worker crash after forecast commit")
            return result

    monkeypatch.setattr(worker_module, "SessionLocal", lambda: session)
    monkeypatch.setattr(worker_module, "DailyAutomationService", CrashAfterCommitService)
    assert worker_module.process_one() is True
    retried = session.get(queue_module.BackgroundJob, job.id)
    assert retried is not None
    assert retried.status == "RETRY"
    retried.available_at = datetime.now(timezone.utc)
    session.commit()
    assert worker_module.process_one() is True
    session.expire_all()
    assert session.get(queue_module.BackgroundJob, job.id).status == "SUCCEEDED"
    assert session.query(Forecast).count() == 1
    session.close()


def test_telegram_link_is_visible_in_a_separate_session(tmp_path):
    first = _session(tmp_path)
    _seed_ready_atm(first)
    user = first.query(User).filter_by(username="daily-test").one()
    user.telegram_chat_id = "daily-test-chat"
    first.commit()
    first.close()

    second = _session(tmp_path)
    linked = NotificationRepository(second).get_linked_user("daily-test-chat")
    assert linked is not None
    assert linked.username == "daily-test"
    second.close()


def test_status_reports_disabled_state_and_latest_ingestion(tmp_path, monkeypatch):
    session = _session(tmp_path)
    _seed_ready_atm(session)
    disabled = replace(config_module.settings, daily_automation_enabled=False)
    monkeypatch.setattr("app.services.daily_automation_service.settings", disabled)
    status = DailyAutomationService.status(session)
    assert status["enabled"] is False
    assert status["last_job"] is None
    assert status["last_successful_ingestion_date"] == "2018-01-20"
    session.close()
