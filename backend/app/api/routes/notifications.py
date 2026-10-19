from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user, require_permission
from app.db.session import get_db
from app.models.auth import User
from app.services.notification_service import (
    NotificationConfigurationError,
    NotificationService,
    verify_webhook_secret,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/telegram/link-token")
def create_telegram_link_token(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return NotificationService(db).create_link_token(user)


@router.get("/telegram/status")
def telegram_status(user: User = Depends(get_current_user)) -> dict[str, object]:
    return NotificationService.telegram_status(user)


@router.post("/test-email", response_model=None)
def send_test_email(
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("users:manage")),
) -> dict[str, object] | JSONResponse:
    try:
        result = NotificationService(db).send_test_email()
    except NotificationConfigurationError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "FAILED",
                "reason": "EMAIL_RECIPIENTS_NOT_CONFIGURED",
                "message": "No configured test-email recipients are available.",
            },
        )
    if result["status"] == "FAILED":
        return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content=result)
    return result


@router.post("/telegram/webhook", status_code=status.HTTP_200_OK)
def telegram_webhook(
    update: dict[str, Any],
    db: Session = Depends(get_db),
    webhook_secret: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> dict[str, str]:
    if not verify_webhook_secret(settings.telegram_webhook_secret, webhook_secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret")
    NotificationService(db).handle_update(update)
    return {"status": "ok"}
