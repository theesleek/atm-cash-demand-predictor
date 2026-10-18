from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.atm import utcnow


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    target: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(255), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    artifact_checksums: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("target", "model_version", name="uq_model_registry_target_version"),
        CheckConstraint("status IN ('TRAINED', 'EVALUATED', 'APPROVED', 'ACTIVE', 'RETIRED')", name="ck_model_registry_status"),
        Index("ix_model_registry_target_status", "target", "status"),
        Index("uq_model_registry_active_target", "target", unique=True, postgresql_where=(status == "ACTIVE"), sqlite_where=(status == "ACTIVE")),
    )
