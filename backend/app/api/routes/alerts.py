from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.models.auth import User
from app.schemas.alert import AlertActionRequest
from app.services.alert_service import AlertNotFoundError, AlertService, AlertStateError

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
def list_alerts(
    atm_id: str | None = None,
    status: Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("alerts:read")),
) -> list[dict[str, object]]:
    return AlertService(db).list_alerts(atm_code=atm_id, status=status, limit=limit, offset=offset)


@router.get("/{alert_id}")
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("alerts:read")),
) -> dict[str, object]:
    try:
        return AlertService(db).get_alert(alert_id)
    except AlertNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    request: AlertActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("alerts:acknowledge")),
) -> dict[str, object]:
    try:
        return AlertService(db).acknowledge(
            alert_id,
            user.username,
            request.source,
            user_id=user.id,
        )
    except AlertNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AlertStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{alert_id}/resolve")
def resolve_alert(
    alert_id: int,
    request: AlertActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("alerts:resolve")),
) -> dict[str, object]:
    try:
        return AlertService(db).resolve(
            alert_id,
            user.username,
            request.source,
            user_id=user.id,
        )
    except AlertNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AlertStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
