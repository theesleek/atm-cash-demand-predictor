from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=128)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9_.@-]+$")
    password: str = Field(min_length=12, max_length=72)
    role: Literal["SUPER_ADMIN", "BANK_MANAGER", "OPERATIONS_OFFICER", "ANALYST", "VIEWER"]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: dict[str, object]
