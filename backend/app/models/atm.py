from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text as sql_text
from sqlalchemy.orm import Mapped, relationship, mapped_column

from app.db.base import Base


FORECAST_TYPE_WITHDRAWAL_DEMAND = "withdrawal_demand"
FORECAST_TYPE_SIGNED_FLOW = "signed_flow"
FORECAST_TYPES = frozenset({FORECAST_TYPE_WITHDRAWAL_DEMAND, FORECAST_TYPE_SIGNED_FLOW})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ATM(Base):
    __tablename__ = "atms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    atm_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    branch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    capacity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_cash: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    daily_demand: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    activation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    inventories: Mapped[list["CashInventory"]] = relationship(back_populates="atm", cascade="all, delete-orphan")
    forecasts: Mapped[list["Forecast"]] = relationship(back_populates="atm", cascade="all, delete-orphan")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="atm", cascade="all, delete-orphan")
    replenishments: Mapped[list["Replenishment"]] = relationship(back_populates="atm", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive', 'maintenance', 'warning', 'critical', 'PENDING', 'ACTIVE', 'INACTIVE', 'RETIRED')", name="ck_atms_status"),
        CheckConstraint("capacity >= 0 AND current_cash >= 0 AND daily_demand >= 0", name="ck_atms_nonnegative_values"),
        Index("ix_atms_region_status", "region", "status"),
    )


class CashInventory(Base):
    __tablename__ = "cash_inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    atm_id: Mapped[int] = mapped_column(ForeignKey("atms.id"), nullable=False, index=True)
    inventory_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    cash_on_hand: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    capacity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="healthy", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    atm: Mapped[ATM] = relationship(back_populates="inventories")
    __table_args__ = (
        CheckConstraint("cash_on_hand >= 0 AND capacity >= 0", name="ck_cash_inventory_nonnegative_values"),
        CheckConstraint("status IN ('healthy', 'warning', 'critical')", name="ck_cash_inventory_status"),
        Index("ix_cash_inventory_atm_date", "atm_id", "inventory_date"),
    )


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    atm_id: Mapped[int] = mapped_column(ForeignKey("atms.id"), nullable=False, index=True)
    forecast_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    predicted_demand: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_signed_net_cash_flow: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    risk_evaluation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="AVAILABLE", server_default="AVAILABLE")
    risk_evaluation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recommended_top_up: Mapped[float | None] = mapped_column(Float, nullable=True)
    forecast_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=FORECAST_TYPE_SIGNED_FLOW,
        server_default=FORECAST_TYPE_SIGNED_FLOW,
        index=True,
    )
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="phase2-synthetic", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    atm: Mapped[ATM] = relationship(back_populates="forecasts")
    replenishments: Mapped[list["Replenishment"]] = relationship(back_populates="forecast")
    __table_args__ = (
        CheckConstraint(
            "(predicted_demand IS NULL OR predicted_demand >= 0) AND (recommended_top_up IS NULL OR recommended_top_up >= 0)",
            name="ck_forecasts_nonnegative_values",
        ),
        CheckConstraint("risk_level IN ('NORMAL', 'WARNING', 'HIGH', 'CRITICAL', 'normal', 'warning', 'high', 'critical')", name="ck_forecasts_risk_level"),
        CheckConstraint("forecast_type IN ('withdrawal_demand', 'signed_flow')", name="ck_forecasts_type"),
        UniqueConstraint("atm_id", "forecast_date", "model_version", "forecast_type", name="uq_forecasts_atm_date_model"),
        Index("ix_forecasts_atm_date", "atm_id", "forecast_date"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    atm_id: Mapped[int] = mapped_column(ForeignKey("atms.id"), nullable=False, index=True)
    forecast_id: Mapped[int | None] = mapped_column(ForeignKey("forecasts.id"), nullable=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False, default="CASH_RISK", index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="WARNING", index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN", index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    action_source: Mapped[str] = mapped_column(String(16), nullable=False, default="SYSTEM", server_default="SYSTEM")

    atm: Mapped[ATM] = relationship(back_populates="alerts")
    __table_args__ = (
        CheckConstraint("severity IN ('WARNING', 'HIGH', 'CRITICAL')", name="ck_alerts_severity"),
        CheckConstraint("status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED')", name="ck_alerts_status"),
        CheckConstraint("action_source IN ('SYSTEM', 'WEB', 'API', 'TELEGRAM')", name="ck_alerts_action_source"),
        Index("ix_alerts_atm_status", "atm_id", "status"),
        Index(
            "ix_alerts_active_risk_unique",
            "atm_id",
            "alert_type",
            "severity",
            unique=True,
            postgresql_where=sql_text("status IN ('OPEN', 'ACKNOWLEDGED')"),
            sqlite_where=sql_text("status IN ('OPEN', 'ACKNOWLEDGED')"),
        ),
    )
