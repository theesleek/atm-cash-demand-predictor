from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.routes import activity, alerts, analytics, atms, auth, data_imports, health, notifications, replenishments, websocket
from app.core.config import settings
from app.db.session import SessionLocal, create_db_and_tables, seed_atm_data, seed_security_data
from app.observability import RequestContextMiddleware, configure_logging
from app.metrics import snapshot_metrics
from app.services.notification_service import register_telegram_webhook
from app.services.model_lifecycle_service import ensure_production_model_registered


logger = logging.getLogger(__name__)
configure_logging()

app = FastAPI(
    title="ATM Cash Intelligence API",
    description="MVP backend for signed net cash flow forecasting and replenishment decision support.",
    version="0.1.0",
)

settings.validate()

app.add_middleware(RequestContextMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    content_length = request.headers.get("content-length")
    try:
        body_size = int(content_length) if content_length else 0
    except ValueError:
        return JSONResponse(status_code=400, content={"detail": "Invalid content length"})
    if body_size > settings.request_body_limit_bytes:
        return JSONResponse(status_code=413, content={"detail": "Request body too large"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "Request validation failed", "errors": exc.errors()})


@app.exception_handler(IntegrityError)
async def integrity_exception_handler(_request: Request, _exc: IntegrityError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": "Request conflicts with existing data"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_application_error", extra={"request_id": getattr(request.state, "request_id", None)})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.on_event("startup")
def startup_event() -> None:
    if settings.environment in {"development", "test"}:
        create_db_and_tables()
    db = SessionLocal()
    try:
        seed_atm_data(db)
        seed_security_data(db)
        if settings.environment == "production":
            ensure_production_model_registered(db)
    finally:
        db.close()
    if settings.telegram_webhook_url:
        try:
            register_telegram_webhook()
        except Exception:
            logger.warning("Telegram webhook registration failed", exc_info=False)


app.include_router(health.router)
app.include_router(atms.router)
app.include_router(data_imports.router)
app.include_router(alerts.router)
app.include_router(activity.router)
app.include_router(analytics.router)
app.include_router(auth.router)
app.include_router(replenishments.router)
app.include_router(notifications.router)
app.include_router(websocket.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "ATM Cash Intelligence API is running."}


@app.get("/metrics")
def metrics() -> dict[str, int]:
    return snapshot_metrics()
