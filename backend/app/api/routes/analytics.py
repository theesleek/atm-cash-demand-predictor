from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.ml.model_loader import ModelConfigurationError
from app.models.auth import User
from app.services.data_quality_service import get_data_quality_report
from app.services.model_evaluation_service import get_model_evaluation
from app.services.model_registry_service import get_model_metadata
from app.metrics import increment_metric

router = APIRouter(tags=["analytics"])


@router.get("/forecast/evaluation")
def forecast_evaluation(
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("forecasts:read")),
) -> dict[str, object]:
    try:
        increment_metric("forecast_evaluation_requests_total")
        return get_model_evaluation(session=db)
    except (FileNotFoundError, ValueError, ModelConfigurationError) as exc:
        increment_metric("model_load_failure_total")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/data-quality")
def data_quality(
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("dashboard:read")),
) -> dict[str, object]:
    try:
        return get_data_quality_report(session=db)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/forecast/model-metadata")
def forecast_model_metadata(
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("forecasts:read")),
) -> dict[str, object]:
    try:
        increment_metric("model_metadata_requests_total")
        return get_model_metadata(session=db)
    except (FileNotFoundError, ValueError, OSError, ModelConfigurationError) as exc:
        increment_metric("model_load_failure_total")
        raise HTTPException(status_code=503, detail="Model metadata is unavailable") from exc
