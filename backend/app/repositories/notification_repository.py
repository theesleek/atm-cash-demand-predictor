from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.notification import NotificationDelivery, TelegramLinkToken


class NotificationRepository:
    DELIVERY_LEASE_SECONDS = 300

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _new_claim_token() -> str:
        return uuid4().hex

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

    def claim_delivery(
        self,
        event_type: str,
        channel: str,
        recipient: str,
        idempotency_key: str,
    ) -> tuple[NotificationDelivery, bool]:
        now = datetime.now(timezone.utc)
        delivery = (
            self.session.query(NotificationDelivery)
            .filter(NotificationDelivery.idempotency_key == idempotency_key)
            .with_for_update()
            .first()
        )
        if delivery is not None:
            if delivery.status == "SENT":
                return delivery, False
            if delivery.status == "PROCESSING" and delivery.locked_at is not None:
                locked_at = delivery.locked_at
                if locked_at.tzinfo is None:
                    locked_at = locked_at.replace(tzinfo=timezone.utc)
                if locked_at > now - timedelta(seconds=self.DELIVERY_LEASE_SECONDS):
                    return delivery, False
            delivery.status = "PROCESSING"
            delivery.error = None
            delivery.attempts += 1
            delivery.locked_at = now
            delivery.claim_token = self._new_claim_token()
            self.session.commit()
            return delivery, True

        delivery = NotificationDelivery(
            event_type=event_type,
            channel=channel,
            recipient=recipient,
            status="PROCESSING",
            idempotency_key=idempotency_key,
            attempts=1,
            locked_at=now,
            claim_token=self._new_claim_token(),
        )
        self.session.add(delivery)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = (
                self.session.query(NotificationDelivery)
                .filter(NotificationDelivery.idempotency_key == idempotency_key)
                .first()
            )
            if existing is None:
                raise
            return self.claim_delivery(event_type, channel, recipient, idempotency_key)
        self.session.refresh(delivery)
        return delivery, True

    def finish_delivery(
        self,
        delivery_id: int,
        status: str,
        error: str | None = None,
        *,
        claim_token: str,
    ) -> NotificationDelivery:
        updated = self.session.execute(
            update(NotificationDelivery)
            .where(
                NotificationDelivery.id == delivery_id,
                NotificationDelivery.status == "PROCESSING",
                NotificationDelivery.claim_token == claim_token,
            )
            .values(
                status=status,
                error=error,
                locked_at=None,
                claim_token=None,
            )
        )
        self.session.commit()
        delivery = self.session.get(NotificationDelivery, delivery_id)
        if delivery is None:
            raise LookupError(f"Notification delivery {delivery_id} not found")
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
