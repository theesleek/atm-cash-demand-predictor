from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, inspect, text


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="Set RUN_POSTGRES_INTEGRATION=1 with a reachable PostgreSQL DATABASE_URL",
)


def test_postgres_schema_and_rollback() -> None:
    database_url = os.environ["DATABASE_URL"]
    assert database_url.startswith("postgresql")
    engine = create_engine(database_url, pool_pre_ping=True)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"users", "atms", "forecasts", "alerts", "replenishments", "audit_logs", "background_jobs"} <= tables
    with engine.begin() as connection:
        connection.execute(text("SELECT 1"))
    connection = engine.connect()
    transaction = connection.begin()
    connection.execute(text("INSERT INTO rate_limit_states (key, failures, window_started_at, updated_at) VALUES ('integration', 1, NOW(), NOW())"))
    transaction.rollback()
    assert connection.execute(text("SELECT COUNT(*) FROM rate_limit_states WHERE key = 'integration'")).scalar_one() == 0
    connection.close()
    engine.dispose()
