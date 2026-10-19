from __future__ import annotations

import pytest

from tests.integration.test_notification_reliability_postgres import (
    CONFIRMATION_ENV,
    DATABASE_URL_ENV,
    OPT_IN_ENV,
    validate_disposable_postgres_environment,
)


def _environment(**overrides: str) -> dict[str, str]:
    values = {
        OPT_IN_ENV: "1",
        CONFIRMATION_ENV: "1",
        DATABASE_URL_ENV: "postgresql+psycopg2://test_user:test_password@127.0.0.1:5432/codex_test_notification",
    }
    values.update(overrides)
    return values


def test_postgres_guard_refuses_without_explicit_opt_in() -> None:
    environment = _environment()
    environment.pop(OPT_IN_ENV)

    with pytest.raises(RuntimeError, match=OPT_IN_ENV):
        validate_disposable_postgres_environment(environment)


def test_postgres_guard_refuses_non_test_database_name() -> None:
    with pytest.raises(RuntimeError, match="database names"):
        validate_disposable_postgres_environment(_environment(**{DATABASE_URL_ENV: "postgresql://u:p@127.0.0.1/app"}))


def test_postgres_guard_refuses_non_local_host() -> None:
    with pytest.raises(RuntimeError, match="loopback"):
        validate_disposable_postgres_environment(
            _environment(**{DATABASE_URL_ENV: "postgresql://u:p@db.example.test/codex_test_notification"})
        )
