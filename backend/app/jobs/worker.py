from __future__ import annotations

import argparse
import logging
import time

from app.db.session import SessionLocal
from app.jobs.queue import claim_job, mark_job_failed, mark_job_succeeded
from app.metrics import increment_metric
from app.services.notification_service import NotificationService


logger = logging.getLogger("atm.worker")


def process_one() -> bool:
    session = SessionLocal()
    try:
        job = claim_job(session)
        if job is None:
            return False
        try:
            if job.job_type == "notification.delivery":
                payload = job.payload
                NotificationService(session).notify(
                    str(payload["event_type"]),
                    str(payload["subject"]),
                    str(payload["message"]),
                )
            else:
                raise ValueError(f"Unsupported background job type: {job.job_type}")
        except (RuntimeError, OSError, TimeoutError) as exc:
            mark_job_failed(session, job.id, type(exc).__name__)
            increment_metric("background_job_failure_total")
            logger.warning("background_job_failed", extra={"job_type": job.job_type, "job_id": job.id})
        except Exception as exc:
            mark_job_failed(session, job.id, type(exc).__name__, retryable=False)
            increment_metric("background_job_failure_total")
            logger.exception("background_job_terminal_failure", extra={"job_type": job.job_type, "job_id": job.id})
        else:
            mark_job_succeeded(session, job.id)
            increment_metric("background_job_success_total")
        return True
    finally:
        session.close()


def run_worker(poll_seconds: float = 2.0) -> None:
    logger.info("background_worker_started")
    while True:
        if not process_one():
            time.sleep(poll_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the persistent ATM background worker")
    parser.add_argument("--once", action="store_true", help="Process at most one available job")
    args = parser.parse_args()
    if args.once:
        process_one()
    else:
        run_worker()
