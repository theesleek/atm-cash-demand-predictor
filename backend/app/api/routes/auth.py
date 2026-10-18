from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_permission
from app.db.session import get_db
from app.models.auth import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import CreateUserRequest, LoginRequest, TokenResponse
from app.services.auth_service import (
    AuthService,
    InvalidCredentialsError,
    RoleNotFoundError,
    UserConflictError,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=TokenResponse)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
    source: str = Header(default="API", alias="X-Action-Source"),
) -> TokenResponse:
    if source not in {"WEB", "API"}:
        raise HTTPException(status_code=400, detail="Invalid action source")
    try:
        result = AuthService(db).login(request.username, request.password, source)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return TokenResponse(**result.__dict__)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    source: str = Header(default="API", alias="X-Action-Source"),
) -> None:
    if source not in {"WEB", "API"}:
        raise HTTPException(status_code=400, detail="Invalid action source")
    AuthService(db).logout(user, source)


@router.get("/me")
def current_user(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return AuthService.serialize_user(user, UserRepository(db).last_login_at(user.id))


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("users:manage")),
) -> list[dict[str, object]]:
    return AuthService(db).list_users()


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    request: CreateUserRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users:manage")),
    source: str = Header(default="API", alias="X-Action-Source"),
) -> dict[str, object]:
    if source not in {"WEB", "API"}:
        raise HTTPException(status_code=400, detail="Invalid action source")
    try:
        return AuthService(db).create_user(request.username, request.password, request.role, source, actor.id)
    except UserConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RoleNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
