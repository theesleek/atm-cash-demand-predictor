from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from app.models.auth import AuditLog


class AuditLogRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        user_id: int | None,
        action: str,
        entity_type: str,
        entity_id: str | int | None,
        source: str,
        metadata: dict[str, object] | None = None,
        commit: bool = True,
    ) -> AuditLog:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            source=source,
            metadata_json=metadata or {},
        )
        self.session.add(entry)
        if commit:
            try:
                self.session.commit()
            except Exception:
                self.session.rollback()
                raise
        else:
            self.session.flush()
        self.session.refresh(entry)
        return entry

    def list_recent(self, limit: int = 100) -> list[AuditLog]:
        return self.session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()

    def list_for_entity(self, entity_type: str, entity_id: str | int) -> list[AuditLog]:
        return (
            self.session.query(AuditLog)
            .filter(AuditLog.entity_type == entity_type, AuditLog.entity_id == str(entity_id))
            .order_by(AuditLog.timestamp.asc(), AuditLog.id.asc())
            .all()
        )

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
    ) -> list[AuditLog]:
        query = self.session.query(AuditLog).options(joinedload(AuditLog.user))
        if user_id is not None:
            query = query.filter(AuditLog.user_id == user_id)
        if action is not None:
            query = query.filter(AuditLog.action == action)
        if source is not None:
            query = query.filter(AuditLog.source == source)
        if date_from is not None:
            query = query.filter(AuditLog.timestamp >= date_from)
        if date_before is not None:
            query = query.filter(AuditLog.timestamp < date_before)
        if entity_type is not None:
            query = query.filter(AuditLog.entity_type == entity_type)
        return query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(limit).all()
