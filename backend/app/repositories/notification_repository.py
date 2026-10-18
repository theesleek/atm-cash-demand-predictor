from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.notification import NotificationDelivery, TelegramLinkToken


class NotificationRepository:
    def __init__(self, session: Session):
        self.session = session

    def log_delivery(
        self,
        event_type: str,
        channel: str,
        recipient: str,
        status: str,
        error: str | None = None,
    ) -> NotificationDelivery:
        delivery = NotificationDelivery(
            event_type=event_type,
            channel=channel,
            recipient=recipient,
            status=status,
            error=error,
        )
        self.session.add(delivery)
        self.session.commit()
        self.session.refresh(delivery)
        return delivery

    def linked_users(self) -> list[User]:
        return (
            self.session.query(User)
            .filter(User.is_active.is_(True), User.telegram_chat_id.is_not(None))
            .all()
        )

    def get_linked_user(self, chat_id: str) -> User | None:
        return self.session.query(User).filter(User.telegram_chat_id == chat_id).first()

    def chat_is_linked_to_another_user(self, chat_id: str, user_id: int) -> bool:
        return (
            self.session.query(User)
            .filter(User.telegram_chat_id == chat_id, User.id != user_id)
            .first()
            is not None
        )

    def create_link_token(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        self.session.query(TelegramLinkToken).filter(
            TelegramLinkToken.user_id == user_id,
            TelegramLinkToken.used_at.is_(None),
        ).update({TelegramLinkToken.used_at: datetime.now(timezone.utc)})
        self.session.add(TelegramLinkToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at))
        self.session.commit()

    def consume_link_token(self, token_hash: str, chat_id: str) -> bool:
        now = datetime.now(timezone.utc)
        link_token = self.session.query(TelegramLinkToken).filter(TelegramLinkToken.token_hash == token_hash).first()
        if link_token is None or self.chat_is_linked_to_another_user(chat_id, link_token.user_id):
            return False
        consumed = self.session.execute(
            update(TelegramLinkToken)
            .where(
                TelegramLinkToken.id == link_token.id,
                TelegramLinkToken.used_at.is_(None),
                TelegramLinkToken.expires_at > now,
            )
            .values(used_at=now)
            .execution_options(synchronize_session=False)
        )
        if consumed.rowcount != 1:
            self.session.rollback()
            return False
        linked = self.session.execute(
            update(User)
            .where(
                User.id == link_token.user_id,
                User.is_active.is_(True),
                or_(User.telegram_chat_id.is_(None), User.telegram_chat_id == chat_id),
            )
            .values(telegram_chat_id=chat_id)
            .execution_options(synchronize_session=False)
        )
        if linked.rowcount != 1:
            self.session.rollback()
            return False
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            return False
        return True