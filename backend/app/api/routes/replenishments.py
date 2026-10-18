from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import require_permission, require_web_approval
from app.db.session import get_db
from app.models.auth import User
from app.schemas.replenishment import (
    ApproveReplenishmentRequest,
    CompleteReplenishmentRequest,
    CreateReplenishmentRequest,
    RejectReplenishmentRequest,
    ScheduleReplenishmentRequest,
)
from app.services.replenishment_service import (
    ReplenishmentNotFoundError,
    ReplenishmentService,
    ReplenishmentStateError,
    ReplenishmentValidationError,
)

router = APIRouter(prefix="/replenishments", tags=["replenishments"])


def _raise_replenishment_error(error: Exception) -> None:
    if isinstance(error, ReplenishmentNotFoundError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, ReplenishmentStateError):
        raise HTTPException(status_code=409, detail=str(error)) from error
    if isinstance(error, ReplenishmentValidationError):
        raise HTTPException(status_code=422, detail=str(error)) from error
    raise error


@router.post("", status_code=status.HTTP_201_CREATED)
def create_replenishment(
    request: CreateReplenishmentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("replenishments:create")),
    source: Literal["WEB", "API"] = Header(default="API", alias="X-Action-Source"),
) -> dict[str, object]:
    try:
        return ReplenishmentService(db).create(
            actor=user,
            atm_code=request.atm_id,
            requested_amount=request.requested_amount,
            forecast_id=request.forecast_id,
            submit=request.submit,
            notes=request.notes,
            source=source,
        )
    except (ReplenishmentNotFoundError, ReplenishmentValidationError) as exc:
        _raise_replenishment_error(exc)


@router.get("")
def list_replenishments(
    replenishment_status: Literal[
        "DRAFT", "REQUESTED", "APPROVED", "REJECTED", "SCHEDULED", "COMPLETED", "CANCELLED"
    ] | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("replenishments:read")),
) -> list[dict[str, object]]:
    try:
        return ReplenishmentService(db).list_for_user(user, replenishment_status, limit=limit, offset=offset)
    except ReplenishmentValidationError as exc:
        _raise_replenishment_error(exc)


@router.get("/{replenishment_id}")
def get_replenishment(
    replenishment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("replenishments:read")),
) -> dict[str, object]:
    try:
        return ReplenishmentService(db).get(replenishment_id, user)
    except ReplenishmentNotFoundError as exc:
        _raise_replenishment_error(exc)


@router.get("/{replenishment_id}/audit")
def get_replenishment_audit(
    replenishment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("replenishments:read")),
) -> list[dict[str, object]]:
    try:
        return ReplenishmentService(db).get_audit_history(replenishment_id, user)
    except ReplenishmentNotFoundError as exc:
        _raise_replenishment_error(exc)


@router.post("/{replenishment_id}/submit")
def submit_replenishment(
    replenishment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("replenishments:create")),
    source: Literal["WEB", "API"] = Header(default="API", alias="X-Action-Source"),
) -> dict[str, object]:
    try:
        return ReplenishmentService(db).submit(replenishment_id, user, source)
    except (ReplenishmentNotFoundError, ReplenishmentStateError) as exc:
        _raise_replenishment_error(exc)


@router.post("/{replenishment_id}/cancel")
def cancel_replenishment(
    replenishment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("replenishments:cancel")),
    source: Literal["WEB", "API"] = Header(default="API", alias="X-Action-Source"),
) -> dict[str, object]:
    try:
        return ReplenishmentService(db).cancel(replenishment_id, user, source)
    except (ReplenishmentNotFoundError, ReplenishmentStateError) as exc:
        _raise_replenishment_error(exc)


@router.post("/{replenishment_id}/approve")
def approve_replenishment(
    replenishment_id: int,
    request: ApproveReplenishmentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_web_approval()),
    source: Literal["WEB", "API"] = Header(default="WEB", alias="X-Action-Source"),
) -> dict[str, object]:
    try:
        return ReplenishmentService(db).approve(
            replenishment_id, user, request.approved_amount, request.notes, source
        )
    except (ReplenishmentNotFoundError, ReplenishmentStateError, ReplenishmentValidationError) as exc:
        _raise_replenishment_error(exc)


@router.post("/{replenishment_id}/reject")
def reject_replenishment(
    replenishment_id: int,
    request: RejectReplenishmentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("replenishments:approve")),
    source: Literal["WEB", "API"] = Header(default="API", alias="X-Action-Source"),
) -> dict[str, object]:
    try:
        return ReplenishmentService(db).reject(replenishment_id, user, request.reason, source)
    except (ReplenishmentNotFoundError, ReplenishmentStateError) as exc:
        _raise_replenishment_error(exc)


@router.post("/{replenishment_id}/schedule")
def schedule_replenishment(
    replenishment_id: int,
    request: ScheduleReplenishmentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("replenishments:schedule")),
    source: Literal["WEB", "API"] = Header(default="API", alias="X-Action-Source"),
) -> dict[str, object]:
    try:
        return ReplenishmentService(db).schedule(
            replenishment_id, user, request.scheduled_at, request.notes, source
        )
    except (ReplenishmentNotFoundError, ReplenishmentStateError) as exc:
        _raise_replenishment_error(exc)


@router.post("/{replenishment_id}/complete")
def complete_replenishment(
    replenishment_id: int,
    request: CompleteReplenishmentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("replenishments:complete")),
    source: Literal["WEB", "API"] = Header(default="API", alias="X-Action-Source"),
) -> dict[str, object]:
    try:
        return ReplenishmentService(db).complete(replenishment_id, user, request.notes, source)
    except (ReplenishmentNotFoundError, ReplenishmentStateError) as exc:
        _raise_replenishment_error(exc)
