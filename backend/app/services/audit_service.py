from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.repositories.audit_log_repository import AuditLogRepository


class AuditService:
    def __init__(self, session: Session):
        self.repository = AuditLogRepository(session)

    def record(
        self,
        user_id: int | None,
        action: str,
        entity_type: str,
        entity_id: str | int | None,
        source: str,
        metadata: dict[str, object] | None = None,
        commit: bool = True,
    ) -> None:
        self.repository.create(user_id, action, entity_type, entity_id, source, metadata, commit=commit)

    def list_for_entity(self, entity_type: str, entity_id: str | int) -> list[dict[str, object]]:
        return [
            {
                "audit_id": entry.id,
                "user_id": entry.user_id,
                "username": entry.user.username if entry.user is not None else None,
                "action": entry.action,
                "entity_type": entry.entity_type,
                "entity_id": entry.entity_id,
                "source": entry.source,
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "metadata": entry.metadata_json,
            }
            for entry in self.repository.list_for_entity(entity_type, entity_id)
        ]

    def list_filtered(
        self,
        *,
        user_id: int | None = None,
        action: str | None = None,
        source: str | None = None,
        date_from: datetime | None = None,
        date_before: datetime | None = None,
        entity_type: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        return [
            {
                "audit_id": entry.id,
                "user_id": entry.user_id,
                "username": entry.user.username if entry.user is not None else None,
                "action": entry.action,
                "entity_type": entry.entity_type,
                "entity_id": entry.entity_id,
                "source": entry.source,
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
            }
            for entry in self.repository.list_filtered(
                user_id=user_id,
                action=action,
                source=source,
                date_from=date_from,
                date_before=date_before,
                entity_type=entity_type,
                limit=limit,
            )
        ]
