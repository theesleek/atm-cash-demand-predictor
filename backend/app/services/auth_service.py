from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.passwords import hash_password, verify_password
from app.core.security import create_access_token, token_expiration_seconds
from app.models.auth import User
from app.repositories.user_repository import UserRepository
from app.services.audit_service import AuditService


class InvalidCredentialsError(ValueError):
    pass


class UserConflictError(ValueError):
    pass


class RoleNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class LoginResult:
    access_token: str
    token_type: str
    expires_in: int
    user: dict[str, object]


class AuthService:
    def __init__(self, session: Session):
        self.session = session
        self.users = UserRepository(session)
        self.audit = AuditService(session)

    def login(self, username: str, password: str, source: str = "API") -> LoginResult:
        user = self.users.get_by_username(username.strip())
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            self.audit.record(
                user_id=user.id if user else None,
                action="LOGIN_FAILED",
                entity_type="USER",
                entity_id=user.id if user else None,
                source=source,
                metadata={"username": username.strip().lower()},
            )
            raise InvalidCredentialsError("Invalid username or password")

        access_token = create_access_token(user.id, user.token_version)
        self.audit.record(user.id, "LOGIN_SUCCEEDED", "USER", user.id, source)
        return LoginResult(
            access_token=access_token,
            token_type="bearer",
            expires_in=token_expiration_seconds(),
            user=self.serialize_user(user, self.users.last_login_at(user.id)),
        )

    def logout(self, user: User, source: str) -> None:
        user.token_version += 1
        self.users.save(user)
        self.audit.record(user.id, "LOGOUT", "USER", user.id, source)

    def create_user(self, username: str, password: str, role_name: str, source: str, actor_id: int) -> dict[str, object]:
        normalized_username = username.strip().lower()
        if self.users.get_by_username(normalized_username):
            raise UserConflictError("Username already exists")
        role = self.users.get_role(role_name)
        if role is None:
            raise RoleNotFoundError(f"Unknown role: {role_name}")

        user = self.users.create(normalized_username, hash_password(password), role)
        self.audit.record(
            actor_id,
            "USER_CREATED",
            "USER",
            user.id,
            source,
            {"username": normalized_username, "role": role.name},
        )
        return self.serialize_user(user)

    def list_users(self) -> list[dict[str, object]]:
        return [self.serialize_user(user) for user in self.users.list()]

    @staticmethod
    def serialize_user(user: User, last_login_at: datetime | None = None) -> dict[str, object]:
        return {
            "user_id": user.id,
            "name": None,
            "username": user.username,
            "role": user.role.name,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": last_login_at.isoformat() if last_login_at else None,
        }
