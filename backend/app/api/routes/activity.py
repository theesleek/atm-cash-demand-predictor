from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.models.auth import User
from app.services.audit_service import AuditService

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("")
def list_activity(
    user_id: int | None = None,
    action: str | None = Query(default=None, min_length=1, max_length=64),
    source: Literal["WEB", "API", "SYSTEM", "TELEGRAM"] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    entity_type: str | None = Query(default=None, min_length=1, max_length=64),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("audit:read")),
) -> list[dict[str, object]]:
    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc) if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc) if date_to else None
    return AuditService(db).list_filtered(
        user_id=user_id,
        action=action.upper() if action else None,
        source=source,
        date_from=start,
        date_before=end,
        entity_type=entity_type.upper() if entity_type else None,
        limit=limit,
    )