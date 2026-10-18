from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Callable
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import has_permission
from app.db.session import get_db
from app.models.auth import User
from app.repositories.user_repository import UserRepository


JWT_ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY") or settings.jwt_secret_key
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be configured with at least 32 characters")
    return secret


def token_expiration_seconds() -> int:
    if settings.jwt_expiration_minutes < 1:
        raise RuntimeError("JWT_EXPIRATION_MINUTES must be at least 1")
    return settings.jwt_expiration_minutes * 60


def create_access_token(user_id: int, token_version: int) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),
        "ver": token_version,
        "iat": now,
        "exp": now + timedelta(seconds=token_expiration_seconds()),
        "jti": str(uuid4()),
    }
    return jwt.encode(claims, _jwt_secret(), algorithm=JWT_ALGORITHM)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
        user_id = int(claims["sub"])
        token_version = int(claims["ver"])
    except (JWTError, KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise credentials_error from exc

    user = UserRepository(session).get(user_id)
    if user is None or not user.is_active or user.token_version != token_version:
        raise credentials_error
    return user


def require_permission(permission: str, web_only: bool = False) -> Callable[..., User]:
    def dependency(
        user: User = Depends(get_current_user),
        action_source: str | None = Header(default=None, alias="X-Action-Source"),
    ) -> User:
        if not has_permission(user.role.name, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        if web_only and action_source != "WEB":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This action is web-only")
        return user

    return dependency


def require_web_approval() -> Callable[..., User]:
    return require_permission("replenishments:approve", web_only=True)
