from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateReplenishmentRequest(BaseModel):
    atm_id: str = Field(min_length=1, max_length=64)
    forecast_id: int | None = Field(default=None, gt=0)
    requested_amount: float | None = Field(default=None, gt=0)
    submit: bool = True
    notes: str | None = Field(default=None, max_length=2000)


class ApproveReplenishmentRequest(BaseModel):
    approved_amount: float | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=2000)


class RejectReplenishmentRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class ScheduleReplenishmentRequest(BaseModel):
    scheduled_at: datetime
    notes: str | None = Field(default=None, max_length=2000)


class CompleteReplenishmentRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)
