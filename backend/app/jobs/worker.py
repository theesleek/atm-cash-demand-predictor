from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from app.db.session import SessionLocal
from app.jobs.queue import (
    claim_job,
    dispatch_outbox_once,
    enqueue_daily_forecast_job,
    mark_job_failed,
    mark_job_succeeded,
    update_job_payload,
)
from app.core.config import settings
from app.metrics import increment_metric
from app.services.daily_automation_service import DailyAutomationService
from app.services.notification_service import NotificationService


logger = logging.getLogger("atm.worker")


class DailyJobScheduler:
    """Enqueue at most once per UTC operational date per worker process."""

    def __init__(
        self,
        session_factory: Callable[[], object] = SessionLocal,
        clock: Callable[[], datetime] | None = None,
        retry_backoff_seconds: float = 30.0,
    ) -> None:
        self.session_factory = session_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.retry_backoff_seconds = retry_backoff_seconds
        self.last_triggered_date: date | None = None
        self.retry_date: date | None = None
        self.retry_not_before: datetime | None = None

    def tick(self) -> bool:
        if not settings.daily_automation_enabled:
            return False
        current = self.clock()
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        current = current.astimezone(timezone.utc)
        if self.retry_not_before is not None and current < self.retry_not_before:
            return False
        operational_date = self.retry_date or current.date()
        if self.last_triggered_date == operational_date:
            return False
        session = None
        try:
            session = self.session_factory()
            enqueue_daily_forecast_job(session, operational_date)
            self.last_triggered_date = operational_date
            self.retry_date = None
            self.retry_not_before = None
            return True
        except Exception as exc:
            self.retry_not_before = current + timedelta(seconds=self.retry_backoff_seconds)
            self.retry_date = operational_date
            logger.warning(
                "daily_job_schedule_failed",
                extra={"operational_date": operational_date.isoformat(), "error_type": type(exc).__name__},
            )
            return False
        finally:
            if session is not None:
                session.close()


def process_one() -> bool:
    session = SessionLocal()
    try:
        dispatched = dispatch_outbox_once(session)
        job = claim_job(session)
        if job is None:
            return dispatched
        claim_token = job.claim_token
        if not claim_token:
            raise RuntimeError("Background job claim token is missing")
        try:
            if job.job_type == "notification.delivery":
                payload = job.payload
                results = NotificationService(session).notify(
                    str(payload["event_type"]),
                    str(payload["subject"]),
                    str(payload["message"]),
                    event_key=str(payload["event_key"]) if payload.get("event_key") else None,
                )
                if any(result.get("status") != "SENT" for result in results):
                    raise RuntimeError("Notification delivery was not fully successful")
            elif job.job_type == "daily.forecast_refresh":
                result = DailyAutomationService(session).run(job.payload)
                payload = dict(job.payload)
                payload.update(result)
                if not update_job_payload(session, job.id, payload, claim_token=claim_token):
                    raise RuntimeError("Daily forecast job claim was lost before status update")
            else:
                raise ValueError(f"Unsupported background job type: {job.job_type}")
        except (RuntimeError, OSError, TimeoutError) as exc:
            if job.job_type == "daily.forecast_refresh":
                payload = dict(job.payload)
                payload.update({"run_status": "FAILED", "last_error": type(exc).__name__, "completed_at": None})
                update_job_payload(session, job.id, payload, claim_token=claim_token)
            mark_job_failed(session, job.id, type(exc).__name__, claim_token=claim_token)
            increment_metric("background_job_failure_total")
            logger.warning("background_job_failed", extra={"job_type": job.job_type, "job_id": job.id})
        except Exception as exc:
            if job.job_type == "daily.forecast_refresh":
                payload = dict(job.payload)
                payload.update({"run_status": "FAILED", "last_error": type(exc).__name__, "completed_at": None})
                update_job_payload(session, job.id, payload, claim_token=claim_token)
            mark_job_failed(session, job.id, type(exc).__name__, claim_token=claim_token, retryable=False)
            increment_metric("background_job_failure_total")
            logger.exception("background_job_terminal_failure", extra={"job_type": job.job_type, "job_id": job.id})
        else:
            mark_job_succeeded(session, job.id, claim_token)
            increment_metric("background_job_success_total")
        return True
    finally:
        session.close()


def run_worker(poll_seconds: float = 2.0, scheduler: DailyJobScheduler | None = None) -> None:
    logger.info("background_worker_started")
    daily_scheduler = scheduler or DailyJobScheduler()
    while True:
        daily_scheduler.tick()
        try:
            processed = process_one()
        except Exception as exc:
            logger.warning("background_worker_poll_failed", extra={"error_type": type(exc).__name__})
            time.sleep(max(poll_seconds, 30.0))
            continue
        if not processed:
            time.sleep(poll_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the persistent ATM background worker")
    parser.add_argument("--once", action="store_true", help="Process at most one available job")
    args = parser.parse_args()
    if args.once:
        process_one()
    else:
        run_worker()
