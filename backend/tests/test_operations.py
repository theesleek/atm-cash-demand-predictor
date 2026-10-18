from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.rate_limit import distributed_record_failure, distributed_retry_after
from app.db.base import Base
from app.jobs.queue import claim_job, enqueue_job, mark_job_failed
from app.models import atm, auth, notification, operations, replenishment  # noqa: F401


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_background_jobs_are_deduplicated_and_retryable() -> None:
    session = _session()
    first = enqueue_job(session, "notification.delivery", {"message": "x"}, dedupe_key="event-1", max_attempts=2)
    duplicate = enqueue_job(session, "notification.delivery", {"message": "x"}, dedupe_key="event-1", max_attempts=2)
    claimed = claim_job(session)
    assert first.id == duplicate.id
    assert claimed is not None
    mark_job_failed(session, claimed.id, "RuntimeError")
    assert session.get(operations.BackgroundJob, claimed.id).status == "RETRY"
    session.close()


def test_login_rate_limit_state_is_shared_through_database() -> None:
    session = _session()
    key = "127.0.0.1:login"
    for _ in range(3):
        distributed_record_failure(session, key, attempts=3, window_seconds=60, block_seconds=30)
    assert distributed_retry_after(session, key) > 0
    session.close()
