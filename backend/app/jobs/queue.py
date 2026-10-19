from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
from uuid import uuid4

from sqlalchemy import case, or_, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.operations import BackgroundJob, NotificationOutbox


logger = logging.getLogger(__name__)
JOB_LEASE_SECONDS = 300
OUTBOX_LEASE_SECONDS = 300
DEFAULT_MAX_ATTEMPTS = 5
DAILY_FORECAST_JOB_TYPE = "daily.forecast_refresh"


def _new_claim_token() -> str:
    return uuid4().hex


def enqueue_job(
    session: Session,
    job_type: str,
    payload: dict[str, object],
    *,
    dedupe_key: str | None = None,
    max_attempts: int = 5,
) -> BackgroundJob:
    job = BackgroundJob(
        job_type=job_type,
        dedupe_key=dedupe_key,
        payload=payload,
        status="QUEUED",
        max_attempts=max_attempts,
    )
    session.add(job)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        if dedupe_key is None:
            raise
        existing = (
            session.query(BackgroundJob)
            .filter(BackgroundJob.job_type == job_type, BackgroundJob.dedupe_key == dedupe_key)
            .one()
        )
        return existing
    session.refresh(job)
    return job


def daily_forecast_dedupe_key(operational_date: date) -> str:
    return f"daily-forecast:{operational_date.isoformat()}"


def enqueue_daily_forecast_job(
    session: Session,
    operational_date: date,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> BackgroundJob | None:
    """Enqueue one operator-enabled daily forecast refresh for a UTC date."""
    if not settings.daily_automation_enabled:
        return None
    return enqueue_job(
        session,
        DAILY_FORECAST_JOB_TYPE,
        {
            "operational_date": operational_date.isoformat(),
            "run_status": "QUEUED",
            "forecasts_created": 0,
            "skipped_atms": [],
            "failed_atms": [],
        },
        dedupe_key=daily_forecast_dedupe_key(operational_date),
        max_attempts=max_attempts,
    )


def update_job_payload(
    session: Session,
    job_id: int,
    payload: dict[str, object],
    *,
    claim_token: str,
) -> bool:
    updated = session.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.id == job_id,
            BackgroundJob.status == "PROCESSING",
            BackgroundJob.claim_token == claim_token,
        )
        .values(payload=payload)
    )
    session.commit()
    return bool(updated.rowcount)


def stage_notification(
    session: Session,
    event_key: str,
    event_type: str,
    subject: str,
    message: str,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> NotificationOutbox:
    values = {
        "event_key": event_key,
        "event_type": event_type,
        "subject": subject,
        "message": message,
        "status": "PENDING",
        "max_attempts": max_attempts,
    }
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        statement = postgresql_insert(NotificationOutbox).values(**values).on_conflict_do_nothing(
            index_elements=["event_key"]
        )
    elif dialect == "sqlite":
        statement = sqlite_insert(NotificationOutbox).values(**values).on_conflict_do_nothing(
            index_elements=["event_key"]
        )
    else:
        # The application supports PostgreSQL and SQLite. Keep a safe fallback
        # for schema tooling using another SQLAlchemy dialect.
        existing = session.query(NotificationOutbox).filter(NotificationOutbox.event_key == event_key).first()
        if existing is not None:
            return existing
        session.add(NotificationOutbox(**values))
        session.flush()
        return session.query(NotificationOutbox).filter(NotificationOutbox.event_key == event_key).one()

    session.execute(statement)
    session.flush()
    return session.query(NotificationOutbox).filter(NotificationOutbox.event_key == event_key).one()


def _recover_stale_jobs(session: Session, now: datetime) -> int:
    stale_before = now - timedelta(seconds=JOB_LEASE_SECONDS)
    result = session.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.status == "PROCESSING",
            or_(BackgroundJob.locked_at.is_(None), BackgroundJob.locked_at < stale_before),
        )
        .values(
            status=case(
                (BackgroundJob.attempts >= BackgroundJob.max_attempts, "FAILED"),
                else_="RETRY",
            ),
            available_at=now,
            locked_at=None,
            claim_token=None,
        )
        .execution_options(synchronize_session=False)
    )
    session.commit()
    return result.rowcount or 0


def _recover_stale_outbox(session: Session, now: datetime) -> int:
    stale_before = now - timedelta(seconds=OUTBOX_LEASE_SECONDS)
    result = session.execute(
        update(NotificationOutbox)
        .where(
            NotificationOutbox.status == "PROCESSING",
            or_(NotificationOutbox.locked_at.is_(None), NotificationOutbox.locked_at < stale_before),
        )
        .values(
            status=case(
                (NotificationOutbox.attempts >= NotificationOutbox.max_attempts, "FAILED"),
                else_="RETRY",
            ),
            available_at=now,
            locked_at=None,
            claim_token=None,
        )
        .execution_options(synchronize_session=False)
    )
    session.commit()
    return result.rowcount or 0


def _mark_outbox_dispatch_failed(session: Session, outbox_id: int, claim_token: str, error: str) -> None:
    outbox = (
        session.query(NotificationOutbox)
        .filter(
            NotificationOutbox.id == outbox_id,
            NotificationOutbox.status == "PROCESSING",
            NotificationOutbox.claim_token == claim_token,
        )
        .first()
    )
    if outbox is None:
        session.rollback()
        return
    status = "FAILED" if outbox.attempts >= outbox.max_attempts else "RETRY"
    available_at = datetime.now(timezone.utc) + timedelta(
        seconds=min(300, 2 ** max(outbox.attempts - 1, 0))
    )
    updated = session.execute(
        update(NotificationOutbox)
        .where(
            NotificationOutbox.id == outbox_id,
            NotificationOutbox.status == "PROCESSING",
            NotificationOutbox.claim_token == claim_token,
        )
        .values(
            status=status,
            available_at=available_at,
            locked_at=None,
            claim_token=None,
            last_error=error[:1000],
        )
    )
    if updated.rowcount == 0:
        session.rollback()
        return
    session.commit()


def dispatch_outbox_once(session: Session) -> bool:
    """Move one durable outbox event into the worker queue."""
    now = datetime.now(timezone.utc)
    _recover_stale_outbox(session, now)
    outbox = (
        session.query(NotificationOutbox)
        .filter(
            NotificationOutbox.status.in_({"PENDING", "RETRY"}),
            NotificationOutbox.available_at <= now,
        )
        .order_by(NotificationOutbox.available_at.asc(), NotificationOutbox.id.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if outbox is None:
        return False

    outbox.status = "PROCESSING"
    outbox.attempts += 1
    outbox.locked_at = now
    outbox.claim_token = _new_claim_token()
    claim_token = outbox.claim_token
    session.commit()
    outbox_id = outbox.id

    try:
        existing_job = (
            session.query(BackgroundJob)
            .filter(
                BackgroundJob.job_type == "notification.delivery",
                BackgroundJob.dedupe_key == outbox.event_key,
            )
            .first()
        )
        if existing_job is None:
            session.add(
                BackgroundJob(
                    job_type="notification.delivery",
                    dedupe_key=outbox.event_key,
                    payload={
                        "event_key": outbox.event_key,
                        "event_type": outbox.event_type,
                        "subject": outbox.subject,
                        "message": outbox.message,
                    },
                    status="QUEUED",
                    max_attempts=outbox.max_attempts,
                )
            )
        updated = session.execute(
            update(NotificationOutbox)
            .where(
                NotificationOutbox.id == outbox_id,
                NotificationOutbox.status == "PROCESSING",
                NotificationOutbox.claim_token == claim_token,
            )
            .values(
                status="DISPATCHED",
                dispatched_at=datetime.now(timezone.utc),
                locked_at=None,
                claim_token=None,
                last_error=None,
            )
        )
        if updated.rowcount == 0:
            # The queue insert is still safe to commit because its dedupe key
            # is the event key. A newer claimant owns the outbox state.
            session.commit()
            return True
        session.commit()
    except IntegrityError:
        session.rollback()
        existing_job = (
            session.query(BackgroundJob)
            .filter(
                BackgroundJob.job_type == "notification.delivery",
                BackgroundJob.dedupe_key == outbox.event_key,
            )
            .first()
        )
        if existing_job is not None:
            updated = session.execute(
                update(NotificationOutbox)
                .where(
                    NotificationOutbox.id == outbox_id,
                    NotificationOutbox.status == "PROCESSING",
                    NotificationOutbox.claim_token == claim_token,
                )
                .values(
                    status="DISPATCHED",
                    dispatched_at=datetime.now(timezone.utc),
                    locked_at=None,
                    claim_token=None,
                    last_error=None,
                )
            )
            session.commit()
        else:
            _mark_outbox_dispatch_failed(session, outbox_id, claim_token, "IntegrityError")
    except Exception as exc:
        session.rollback()
        logger.warning("notification_outbox_dispatch_failed", extra={"error_type": type(exc).__name__})
        _mark_outbox_dispatch_failed(session, outbox_id, claim_token, type(exc).__name__)
    return True


def claim_job(session: Session) -> BackgroundJob | None:
    now = datetime.now(timezone.utc)
    _recover_stale_jobs(session, now)
    query = (
        session.query(BackgroundJob)
        .filter(
            BackgroundJob.status.in_({"QUEUED", "RETRY"}),
            BackgroundJob.available_at <= now,
        )
        .order_by(BackgroundJob.available_at.asc(), BackgroundJob.id.asc())
        .with_for_update(skip_locked=True)
    )
    job = query.first()
    if job is None:
        return None
    job.status = "PROCESSING"
    job.attempts += 1
    job.locked_at = now
    job.claim_token = _new_claim_token()
    session.commit()
    session.refresh(job)
    return job


def mark_job_succeeded(session: Session, job_id: int, claim_token: str) -> bool:
    updated = session.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.id == job_id,
            BackgroundJob.status == "PROCESSING",
            BackgroundJob.claim_token == claim_token,
        )
        .values(
            status="SUCCEEDED",
            completed_at=datetime.now(timezone.utc),
            locked_at=None,
            claim_token=None,
            last_error=None,
        )
    )
    session.commit()
    return bool(updated.rowcount)

def mark_job_failed(
    session: Session,
    job_id: int,
    error: str,
    *,
    claim_token: str,
    retryable: bool = True,
) -> bool:
    job = (
        session.query(BackgroundJob)
        .filter(
            BackgroundJob.id == job_id,
            BackgroundJob.status == "PROCESSING",
            BackgroundJob.claim_token == claim_token,
        )
        .first()
    )
    if job is None:
        session.rollback()
        return False
    terminal = not retryable or job.attempts >= job.max_attempts
    values: dict[str, object] = {
        "status": "FAILED" if terminal else "RETRY",
        "last_error": error[:1000],
        "locked_at": None,
        "claim_token": None,
    }
    if not terminal:
        delay = min(300, 2 ** max(job.attempts - 1, 0))
        values["available_at"] = datetime.now(timezone.utc) + timedelta(seconds=delay)
    updated = session.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.id == job_id,
            BackgroundJob.status == "PROCESSING",
            BackgroundJob.claim_token == claim_token,
        )
        .values(**values)
    )
    if updated.rowcount == 0:
        session.rollback()
        return False
    session.commit()
    return True
