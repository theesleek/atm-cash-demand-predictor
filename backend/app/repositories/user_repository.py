from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.auth import AuditLog, Role, User


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        return self.session.query(User).filter(User.username == username.lower()).first()

    def last_login_at(self, user_id: int) -> datetime | None:
        return (
            self.session.query(AuditLog.timestamp)
            .filter(AuditLog.user_id == user_id, AuditLog.action == "LOGIN_SUCCEEDED")
            .order_by(desc(AuditLog.timestamp), desc(AuditLog.id))
            .limit(1)
            .scalar()
        )

    def list(self) -> list[User]:
        return self.session.query(User).order_by(User.username.asc()).all()

    def get_role(self, role_name: str) -> Role | None:
        return self.session.query(Role).filter(Role.name == role_name.upper()).first()

    def create(self, username: str, password_hash: str, role: Role) -> User:
        user = User(username=username, password_hash=password_hash, role=role)
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def save(self, user: User) -> User:
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user
