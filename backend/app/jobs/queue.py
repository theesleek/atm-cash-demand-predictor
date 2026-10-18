from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.operations import BackgroundJob


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


def claim_job(session: Session) -> BackgroundJob | None:
    now = datetime.now(timezone.utc)
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
    session.commit()
    session.refresh(job)
    return job


def mark_job_succeeded(session: Session, job_id: int) -> None:
    job = session.get(BackgroundJob, job_id)
    if job is None:
        return
    job.status = "SUCCEEDED"
    job.completed_at = datetime.now(timezone.utc)
    job.locked_at = None
    job.last_error = None
    session.commit()

def mark_job_failed(session: Session, job_id: int, error: str, *, retryable: bool = True) -> None:
    job = session.get(BackgroundJob, job_id)
    if job is None:
        return
    terminal = not retryable or job.attempts >= job.max_attempts
    job.status = "FAILED" if terminal else "RETRY"
    job.last_error = error[:1000]
    job.locked_at = None
    if not terminal:
        delay = min(300, 2 ** max(job.attempts - 1, 0))
        job.available_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
    session.commit()
