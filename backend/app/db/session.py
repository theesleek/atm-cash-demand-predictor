from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.data.atm_data import get_atm_records
from app.db.base import Base
from app.core.passwords import hash_password
from app.models.atm import ATM
from app.models.auth import AuditLog, Role, User
from app.models import notification as notification_models
from app.models import operations as operations_models
from app.models import model_registry as model_registry_models
from app.models import ingestion as ingestion_models
from app.models.replenishment import Replenishment

connect_args: dict[str, Any] = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
pool_options: dict[str, Any] = {
    "pool_pre_ping": True,
    "pool_recycle": 1800,
}
if not settings.database_url.startswith("sqlite"):
    pool_options.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
    )
engine = create_engine(settings.database_url, connect_args=connect_args, **pool_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_db_and_tables() -> None:
    Base.metadata.create_all(bind=engine)
    _upgrade_alert_schema()
    _upgrade_user_schema()
    _upgrade_atm_schema()


def _upgrade_atm_schema() -> None:
    inspector = inspect(engine)
    if "atms" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("atms")}
    with engine.begin() as connection:
        if "location" not in existing_columns:
            connection.execute(text("ALTER TABLE atms ADD COLUMN location VARCHAR(255)"))
        if "activation_date" not in existing_columns:
            connection.execute(text("ALTER TABLE atms ADD COLUMN activation_date DATE"))


def _upgrade_user_schema() -> None:
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    if "telegram_chat_id" not in existing_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE users ADD COLUMN telegram_chat_id VARCHAR(64)"))
    with engine.begin() as connection:
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_telegram_chat_id ON users (telegram_chat_id)")
        )


def _upgrade_alert_schema() -> None:
    inspector = inspect(engine)
    if "alerts" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("alerts")}
    missing_columns = {
        "forecast_id": "INTEGER REFERENCES forecasts(id)",
        "acknowledged_by": "VARCHAR(128)",
        "acknowledged_at": "DATETIME",
        "resolved_by": "VARCHAR(128)",
        "action_source": "VARCHAR(16) NOT NULL DEFAULT 'SYSTEM'",
    }
    with engine.begin() as connection:
        for column_name, column_type in missing_columns.items():
            if column_name not in existing_columns:
                connection.execute(text(f"ALTER TABLE alerts ADD COLUMN {column_name} {column_type}"))
        connection.execute(text("UPDATE alerts SET status = UPPER(status)"))
        connection.execute(text("UPDATE alerts SET severity = UPPER(severity)"))
        connection.execute(text("UPDATE alerts SET alert_type = UPPER(alert_type)"))


def seed_atm_data(session: Session) -> None:
    if session.query(ATM).count() > 0:
        return

    for row in get_atm_records():
        session.add(
            ATM(
                atm_code=str(row["atm_code"]),
                branch_id=str(row["branch_id"]),
                region=str(row["region"]),
                capacity=float(row["capacity"]),
                current_cash=float(row["current_cash"]),
                status=str(row.get("status", "active")),
                daily_demand=float(row["daily_demand"]),
            )
        )

    session.commit()


def seed_security_data(session: Session) -> None:
    from app.core.permissions import ROLE_DESCRIPTIONS

    for role_name, description in ROLE_DESCRIPTIONS.items():
        if session.query(Role).filter(Role.name == role_name).first() is None:
            session.add(Role(name=role_name, description=description))
    session.commit()

    username = settings.bootstrap_admin_username
    password = settings.bootstrap_admin_password
    if not username or not password:
        return
    normalized_username = username.strip().lower()
    if not normalized_username or session.query(User).filter(User.username == normalized_username).first():
        return
    admin_role = session.query(Role).filter(Role.name == "SUPER_ADMIN").one()
    session.add(
        User(
            username=normalized_username,
            password_hash=hash_password(password),
            role_id=admin_role.id,
        )
    )
    session.commit()
