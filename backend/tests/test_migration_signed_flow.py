from __future__ import annotations

import importlib.util
from pathlib import Path


MIGRATION_PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0005_signed_flow_risk_status.py"
SPEC = importlib.util.spec_from_file_location("signed_flow_migration", MIGRATION_PATH)
assert SPEC is not None and SPEC.loader is not None
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


class _Dialect:
    def __init__(self, name: str):
        self.name = name


class _Result:
    def first(self):
        return None


class _Bind:
    def __init__(self, dialect_name: str):
        self.dialect = _Dialect(dialect_name)

    def execute(self, _statement):
        return _Result()


class _RecordingOperations:
    def __init__(self, dialect_name: str):
        self.bind = _Bind(dialect_name)
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def get_bind(self):
        return self.bind

    def batch_alter_table(self, *args, **kwargs):
        raise AssertionError("PostgreSQL migration must not rebuild forecasts")

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))

        return record


def _call_names(operations: _RecordingOperations) -> list[str]:
    return [name for name, _args, _kwargs in operations.calls]


def test_postgresql_upgrade_changes_forecasts_in_place(monkeypatch):
    operations = _RecordingOperations("postgresql")
    monkeypatch.setattr(migration, "op", operations)

    migration.upgrade()

    names = _call_names(operations)
    assert "batch_alter_table" not in names
    assert names.count("alter_column") == 3
    assert names.count("add_column") == 3
    assert names.count("drop_constraint") == 1
    assert names.count("create_check_constraint") == 1
    assert all("CASCADE" not in repr(call).upper() for call in operations.calls)
    assert all("pkey" not in repr(call).lower() for call in operations.calls)


def test_postgresql_downgrade_changes_forecasts_in_place(monkeypatch):
    operations = _RecordingOperations("postgresql")
    monkeypatch.setattr(migration, "op", operations)

    migration.downgrade()

    names = _call_names(operations)
    assert "batch_alter_table" not in names
    assert names.count("drop_column") == 3
    assert names.count("alter_column") == 3
    assert names.count("drop_constraint") == 1
    assert names.count("create_check_constraint") == 1
    assert all("CASCADE" not in repr(call).upper() for call in operations.calls)
    assert all("pkey" not in repr(call).lower() for call in operations.calls)
