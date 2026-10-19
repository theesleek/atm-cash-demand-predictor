from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.ml.model_loader import ModelConfigurationError
from app.models.auth import User
from app.schemas.atm import ATMCreate, ATMUpdate
from app.services.atm_service import ATMService
from app.services.daily_automation_service import DailyAutomationService

router = APIRouter(tags=["atms"])


@router.post("/atms", status_code=201)
def create_atm(
    payload: ATMCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("atms:create", web_only=True)),
) -> dict[str, object]:
    try:
        return ATMService(db).create_atm(payload.model_dump(), user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/atms/{atm_id}")
def update_atm(
    atm_id: str,
    payload: ATMUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("atms:update", web_only=True)),
) -> dict[str, object]:
    try:
        record = ATMService(db).update_atm(atm_id, payload.model_dump(exclude_unset=True), user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail=f"ATM {atm_id} not found")
    return record


@router.get("/atms")
def list_atms(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("dashboard:read")),
) -> list[dict[str, object]]:
    return ATMService(db).list_atms(limit=limit, offset=offset)


@router.get("/atms/network")
def list_atm_network(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard:read")),
) -> list[dict[str, object]]:
    return ATMService(db).list_network_atms(user.id, user.role.name, limit=limit, offset=offset)


@router.get("/atms/{atm_id}")
def get_atm(
    atm_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("dashboard:read")),
) -> dict[str, object]:
    record = ATMService(db).get_atm(atm_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"ATM {atm_id} not found")
    return record


@router.get("/atms/{atm_id}/intelligence")
def get_atm_intelligence(
    atm_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("forecasts:read")),
) -> dict[str, object]:
    record = ATMService(db).get_atm_intelligence(atm_id, user.id, user.role.name)
    if record is None:
        raise HTTPException(status_code=404, detail=f"ATM {atm_id} not found")
    return record


@router.get("/atms/{atm_id}/readiness")
def get_atm_readiness(
    atm_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("dashboard:read")),
) -> dict[str, object]:
    record = ATMService(db).get_readiness(atm_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"ATM {atm_id} not found")
    return record


@router.get("/forecast")
def get_forecast(
    atm_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("forecasts:read")),
) -> dict[str, object]:
    service = ATMService(db)
    try:
        return service.get_forecast(atm_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ModelConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/forecasts/{forecast_id}")
def get_persisted_forecast(
    forecast_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("forecasts:read")),
) -> dict[str, object]:
    record = ATMService(db).get_persisted_forecast(forecast_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Forecast {forecast_id} not found")
    return record


@router.get("/dashboard/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("dashboard:read")),
) -> dict[str, object]:
    return ATMService(db).get_dashboard_summary()


@router.get("/automation/status")
def automation_status(
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("dashboard:read")),
) -> dict[str, object]:
    return DailyAutomationService.status(db)
