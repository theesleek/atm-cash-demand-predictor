from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ATMBase(BaseModel):
    atm_code: str = Field(..., min_length=3, max_length=64)
    branch_id: str = Field(..., min_length=2, max_length=64)
    region: str = Field(..., min_length=2, max_length=128)
    location: str | None = Field(default=None, max_length=255)
    capacity: float = Field(..., ge=0)
    current_cash: float = Field(..., ge=0)
    status: str = Field(default="active")
    daily_demand: float = Field(default=0.0, ge=0)
    activation_date: date | None = None


class ATMCreate(BaseModel):
    atm_code: str = Field(..., min_length=3, max_length=64)
    location: str | None = Field(default=None, max_length=255)
    branch_id: str = Field(..., min_length=2, max_length=64)
    region: str = Field(..., min_length=2, max_length=128)
    capacity: float = Field(..., ge=0)
    status: str = Field(default="PENDING")
    activation_date: date | None = None


class ATMUpdate(BaseModel):
    location: str | None = Field(default=None, max_length=255)
    branch_id: str | None = Field(default=None, min_length=2, max_length=64)
    region: str | None = Field(default=None, min_length=2, max_length=128)
    capacity: float | None = Field(default=None, ge=0)
    status: str | None = None
    activation_date: date | None = None


class ATMRead(ATMBase):
    id: int

    model_config = {"from_attributes": True}
