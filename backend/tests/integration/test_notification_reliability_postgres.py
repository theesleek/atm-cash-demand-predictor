from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Barrier
from typing import Mapping
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

# Keep this test suite from implicitly loading developer or production dotenv files.
os.environ.setdefault("PYTHON_DOTENV_DISABLED", "1")

from app.jobs import queue
from app.models import atm, auth, notification, operations, replenishment  # noqa: F401
from app.models.notification import NotificationDelivery
from app.models.operations import BackgroundJob, NotificationOutbox
from app.repositories.notification_repository import NotificationRepository


pytestmark = pytest.mark.integration


OPT_IN_ENV = "ATM_ALLOW_DISPOSABLE_POSTGRES_TESTS"
CONFIRMATION_ENV = "ATM_CONFIRM_DISPOSABLE_POSTGRES_DB"
DATABASE_URL_ENV = "DATABASE_URL"
ALLOWED_DATABASE_PREFIXES = ("codex_test_", "test_notification_")
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
REJECTED_HOST_MARKERS = ("neon", "render", "production", "prod")


@dataclass(frozen=True)
class DisposablePostgresConfig:
    database_url: str
    database_name: str


def validate_disposable_postgres_environment(environ: Mapping[str, str]) -> DisposablePostgresConfig:
    """Validate test-only PostgreSQL settings without opening a connection."""
    if environ.get(OPT_IN_ENV) != "1":
        raise RuntimeError(f"Set {OPT_IN_ENV}=1 to enable disposable PostgreSQL tests")
    if environ.get(CONFIRMATION_ENV) != "1":
        raise RuntimeError(f"Set {CONFIRMATION_ENV}=1 to confirm a disposable test database")

    database_url = environ.get(DATABASE_URL_ENV, "")
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
        raise RuntimeError("Disposable PostgreSQL tests require a PostgreSQL DATABASE_URL")
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if hostname not in LOOPBACK_HOSTS:
        raise RuntimeError("Disposable PostgreSQL tests require a loopback database host")
    if any(marker in hostname for marker in REJECTED_HOST_MARKERS):
        raise RuntimeError("Production and hosted PostgreSQL hosts are not permitted")

    database_name = parsed.path.lstrip("/")
    if not database_name or "/" in database_name:
        raise RuntimeError("DATABASE_URL must name one dedicated disposable test database")
    if not database_name.startswith(ALLOWED_DATABASE_PREFIXES):
        raise RuntimeError(
            "Disposable PostgreSQL database names must start with codex_test_ or test_notification_"
        )
    return DisposablePostgresConfig(database_url=database_url, database_name=database_name)


@pytest.fixture(scope="module")
def postgres_engine():
    config = validate_disposable_postgres_environment(os.environ)
    engine = create_engine(config.database_url, pool_pre_ping=True, pool_size=8, max_overflow=4)
    try:
        with engine.connect() as connection:
            actual_database = connection.exec_driver_sql("SELECT current_database()").scalar_one()
            if actual_database != config.database_name:
                raise RuntimeError("Connected database does not match the verified disposable database name")

        repository_root = Path(__file__).resolve().parents[3]
        alembic_config = Config(str(repository_root / "alembic.ini"))
        try:
            command.upgrade(alembic_config, "head")
        except Exception as exc:
            raise RuntimeError("Alembic migration to head failed for the disposable PostgreSQL database") from exc

        with engine.connect() as connection:
            actual_database = connection.exec_driver_sql("SELECT current_database()").scalar_one()
            revision = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one_or_none()
            if actual_database != config.database_name:
                raise RuntimeError("Database identity changed during disposable PostgreSQL test setup")
            expected_revision = ScriptDirectory.from_config(alembic_config).get_current_head()
            if revision != expected_revision:
                raise RuntimeError(f"Expected Alembic head {expected_revision} is not installed")
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def clear_disposable_notification_rows(postgres_engine):
    with Session(postgres_engine) as session:
        session.query(NotificationOutbox).delete(synchronize_session=False)
        session.query(BackgroundJob).delete(synchronize_session=False)
        session.query(NotificationDelivery).delete(synchronize_session=False)
        session.commit()


def _run_pair(engine, operation):
    barrier = Barrier(2)

    def invoke():
        with Session(engine) as session:
            barrier.wait(timeout=30)
            return operation(session)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(invoke), executor.submit(invoke)]
        return [future.result(timeout=60) for future in futures]


def test_duplicate_outbox_staging_is_deduplicated_with_independent_sessions(postgres_engine) -> None:
    event_key = f"postgres-duplicate-outbox-{uuid4().hex}"

    def stage(session: Session) -> int:
        outbox = queue.stage_notification(session, event_key, "TEST", "Subject", "Message")
        session.commit()
        return outbox.id

    ids = _run_pair(postgres_engine, stage)

    with Session(postgres_engine) as session:
        assert ids[0] == ids[1]
        assert session.query(NotificationOutbox).filter_by(event_key=event_key).count() == 1


def test_competing_background_job_claims_are_exclusive(postgres_engine) -> None:
    dedupe_key = f"postgres-competing-job-{uuid4().hex}"
    with Session(postgres_engine) as session:
        job = queue.enqueue_job(
            session,
            "notification.delivery",
            {"event_key": dedupe_key},
            dedupe_key=dedupe_key,
        )
        job_id = job.id

    def claim(session: Session):
        claimed = queue.claim_job(session)
        return None if claimed is None else (claimed.id, claimed.claim_token)

    claims = _run_pair(postgres_engine, claim)

    assert sum(claim is not None for claim in claims) == 1
    assert claims[0] is None or claims[1] is None
    with Session(postgres_engine) as session:
        current = session.get(BackgroundJob, job_id)
        assert current is not None
        assert current.status == "PROCESSING"
        assert current.claim_token is not None


def test_competing_outbox_claims_dispatch_once(postgres_engine) -> None:
    event_key = f"postgres-competing-outbox-{uuid4().hex}"
    with Session(postgres_engine) as session:
        outbox = queue.stage_notification(session, event_key, "TEST", "Subject", "Message")
        session.commit()
        outbox_id = outbox.id

    results = _run_pair(postgres_engine, queue.dispatch_outbox_once)

    assert sum(results) == 1
    with Session(postgres_engine) as session:
        current = session.get(NotificationOutbox, outbox_id)
        assert current is not None
        assert current.status == "DISPATCHED"
        assert session.query(BackgroundJob).filter_by(dedupe_key=event_key).count() == 1


def test_competing_notification_delivery_claims_are_exclusive(postgres_engine) -> None:
    idempotency_key = f"postgres-competing-delivery-{uuid4().hex}"

    def claim(session: Session):
        delivery, should_send = NotificationRepository(session).claim_delivery(
            "TEST", "EMAIL", "recipient@example.test", idempotency_key
        )
        return delivery.id, should_send

    claims = _run_pair(postgres_engine, claim)

    assert claims[0][0] == claims[1][0]
    assert sorted(claim[1] for claim in claims) == [False, True]
    with Session(postgres_engine) as session:
        assert session.query(NotificationDelivery).filter_by(idempotency_key=idempotency_key).count() == 1


def test_stale_background_job_claim_cannot_overwrite_newer_result(postgres_engine) -> None:
    dedupe_key = f"postgres-stale-job-{uuid4().hex}"
    with Session(postgres_engine) as seed:
        job = queue.enqueue_job(seed, "notification.delivery", {"event_key": dedupe_key}, dedupe_key=dedupe_key)
        job_id = job.id

    with Session(postgres_engine) as old_session:
        old_claim = queue.claim_job(old_session)
        assert old_claim is not None and old_claim.claim_token is not None
        old_token = old_claim.claim_token
        old_session.execute(
            update(BackgroundJob)
            .where(BackgroundJob.id == job_id)
            .values(locked_at=datetime.now(timezone.utc) - timedelta(minutes=10))
        )
        old_session.commit()

        with Session(postgres_engine) as new_session:
            new_claim = queue.claim_job(new_session)
            assert new_claim is not None and new_claim.claim_token not in {None, old_token}
            assert not queue.mark_job_succeeded(old_session, job_id, old_token)
            assert queue.mark_job_succeeded(new_session, job_id, new_claim.claim_token)

    with Session(postgres_engine) as session:
        assert session.get(BackgroundJob, job_id).status == "SUCCEEDED"


def test_stale_delivery_claim_cannot_overwrite_newer_result(postgres_engine) -> None:
    idempotency_key = f"postgres-stale-delivery-{uuid4().hex}"
    with Session(postgres_engine) as old_session:
        old_delivery, old_should_send = NotificationRepository(old_session).claim_delivery(
            "TEST", "EMAIL", "stale@example.test", idempotency_key
        )
        assert old_should_send and old_delivery.claim_token is not None
        old_token = old_delivery.claim_token
        old_delivery.locked_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        old_session.commit()

        with Session(postgres_engine) as new_session:
            new_delivery, new_should_send = NotificationRepository(new_session).claim_delivery(
                "TEST", "EMAIL", "stale@example.test", idempotency_key
            )
            assert new_should_send and new_delivery.claim_token not in {None, old_token}
            stale_result = NotificationRepository(old_session).finish_delivery(
                old_delivery.id, "FAILED", "stale", claim_token=old_token
            )
            assert stale_result.status == "PROCESSING"
            final = NotificationRepository(new_session).finish_delivery(
                new_delivery.id, "SENT", claim_token=new_delivery.claim_token
            )
            assert final.status == "SENT"


def test_stale_outbox_claim_cannot_overwrite_newer_result(postgres_engine) -> None:
    event_key = f"postgres-stale-outbox-{uuid4().hex}"
    with Session(postgres_engine) as seed:
        outbox = queue.stage_notification(seed, event_key, "TEST", "Subject", "Message")
        seed.commit()
        outbox_id = outbox.id

    old_token = f"old-{uuid4().hex}"
    new_token = f"new-{uuid4().hex}"
    with Session(postgres_engine) as old_session:
        old_session.execute(
            update(NotificationOutbox)
            .where(NotificationOutbox.id == outbox_id)
            .values(
                status="PROCESSING",
                attempts=1,
                locked_at=datetime.now(timezone.utc) - timedelta(minutes=10),
                claim_token=old_token,
            )
        )
        old_session.commit()

        with Session(postgres_engine) as new_session:
            queue._recover_stale_outbox(new_session, datetime.now(timezone.utc))
            new_session.execute(
                update(NotificationOutbox)
                .where(NotificationOutbox.id == outbox_id)
                .values(status="PROCESSING", locked_at=datetime.now(timezone.utc), claim_token=new_token)
            )
            new_session.commit()
            queue._mark_outbox_dispatch_failed(old_session, outbox_id, old_token, "stale")

    with Session(postgres_engine) as session:
        current = session.get(NotificationOutbox, outbox_id)
        assert current is not None
        assert current.status == "PROCESSING"
        assert current.claim_token == new_token
