from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, relationship, mapped_column

from app.db.base import Base
from app.models.auth import User
from app.models.atm import utcnow

if TYPE_CHECKING:
    from app.models.atm import ATM, Forecast


REPLENISHMENT_STATUSES = (
    "DRAFT",
    "REQUESTED",
    "APPROVED",
    "REJECTED",
    "SCHEDULED",
    "COMPLETED",
    "CANCELLED",
)


class Replenishment(Base):
    __tablename__ = "replenishments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    atm_id: Mapped[int] = mapped_column(ForeignKey("atms.id"), nullable=False, index=True)
    forecast_id: Mapped[int | None] = mapped_column(ForeignKey("forecasts.id"), nullable=True, index=True)
    requested_amount: Mapped[float] = mapped_column(Float, nullable=False)
    approved_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="REQUESTED", index=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    atm: Mapped[ATM] = relationship(back_populates="replenishments")
    forecast: Mapped[Forecast | None] = relationship(back_populates="replenishments")

    __table_args__ = (
        CheckConstraint("requested_amount > 0", name="ck_replenishments_requested_amount_positive"),
        CheckConstraint("approved_amount IS NULL OR approved_amount > 0", name="ck_replenishments_approved_amount_positive"),
        CheckConstraint(
            "status IN ('DRAFT', 'REQUESTED', 'APPROVED', 'REJECTED', 'SCHEDULED', 'COMPLETED', 'CANCELLED')",
            name="ck_replenishments_status",
        ),
        Index("ix_replenishments_status_created", "status", "created_at"),
    )
