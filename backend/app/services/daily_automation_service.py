from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.atm import ATM
from app.models.ingestion import DatasetVersion
from app.models.operations import BackgroundJob
from app.services.atm_service import ATMService
from app.services.notification_service import NotificationService


DAILY_RUN_STATUSES = {"QUEUED", "RUNNING", "COMPLETED", "COMPLETED_WITH_SKIPS", "COMPLETED_WITH_ERRORS", "FAILED"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _notification_summary(outcomes: list[dict[str, object]]) -> str:
    if not outcomes:
        return "not_applicable"
    statuses = {str(item.get("status")) for item in outcomes}
    if "failed" in statuses:
        return "failed"
    if "pending" in statuses:
        return "pending"
    if statuses == {"sent"}:
        return "sent"
    return "pending"


class DailyAutomationService:
    def __init__(self, session: Session):
        self.session = session

    def latest_successful_actual_date(self) -> date | None:
        return self.session.query(func.max(DatasetVersion.date_to)).filter(DatasetVersion.status == "INGESTED").scalar()

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        operational_date = date.fromisoformat(str(payload["operational_date"]))
        latest_actual_date = self.latest_successful_actual_date()
        result: dict[str, object] = {
            "run_status": "RUNNING",
            "started_at": _utcnow().isoformat(),
            "operational_date": operational_date.isoformat(),
            "last_successful_ingestion_date": latest_actual_date.isoformat() if latest_actual_date else None,
            "last_forecast_run_at": None,
            "last_forecast_target_date": None,
            "eligible_atms": 0,
            "forecasts_created": 0,
            "skipped_atms": [],
            "failed_atms": [],
            "notification_status": "not_applicable",
            "notification_outcomes": [],
            "notification_events": [],
            "notification_failures": [],
        }
        atm_service = ATMService(self.session)
        skipped: list[dict[str, object]] = []
        failed: list[dict[str, object]] = []
        notification_outcomes: list[dict[str, object]] = []
        notification_events: list[dict[str, object]] = []
        notification_failures: list[dict[str, object]] = []
        for atm in self.session.query(ATM).order_by(ATM.atm_code.asc()).all():
            readiness = atm_service.ingestion_service.readiness(atm)
            date_to = readiness.get("date_to")
            if readiness.get("status") != "READY":
                skipped.append({"atm_id": atm.atm_code, "reason": str(readiness.get("reason"))})
                continue
            if not date_to:
                skipped.append({"atm_id": atm.atm_code, "reason": "No successfully ingested actual data date is available."})
                continue
            latest_atm_date = date.fromisoformat(str(date_to))
            age_days = (operational_date - latest_atm_date).days
            if age_days > settings.daily_automation_max_data_age_days:
                skipped.append({
                    "atm_id": atm.atm_code,
                    "reason": f"Actual data is stale: latest date {latest_atm_date.isoformat()} is {age_days} days old.",
                })
                continue
            result["eligible_atms"] = int(result["eligible_atms"]) + 1
            try:
                forecast = atm_service.get_forecast(atm.atm_code)
                if forecast.get("forecast_created"):
                    result["forecasts_created"] = int(result["forecasts_created"]) + 1
                result["last_forecast_run_at"] = _utcnow().isoformat()
                result["last_forecast_target_date"] = forecast.get("forecast_date")
                notification = forecast.get("notification") or {"status": "not_applicable"}
                if notification.get("status") != "not_applicable":
                    outcome = {"atm_id": atm.atm_code, **notification}
                    notification_outcomes.append(outcome)
                    notification_events.append({
                        "atm_id": atm.atm_code,
                        "event_type": notification.get("event_type"),
                        "event_key": notification.get("event_key"),
                    })
                    if notification.get("status") == "failed":
                        notification_failures.append(outcome)
            except Exception as exc:
                self.session.rollback()
                failed.append({"atm_id": atm.atm_code, "reason": f"{type(exc).__name__}: {exc}"})

        result["skipped_atms"] = skipped
        result["failed_atms"] = failed
        result["notification_outcomes"] = notification_outcomes
        result["notification_events"] = notification_events
        result["notification_failures"] = notification_failures
        result["notification_status"] = _notification_summary(notification_outcomes)
        if failed or notification_failures:
            result["run_status"] = "COMPLETED_WITH_ERRORS"
        elif skipped:
            result["run_status"] = "COMPLETED_WITH_SKIPS"
        else:
            result["run_status"] = "COMPLETED"
        result["completed_at"] = _utcnow().isoformat()
        return result

    @classmethod
    def status(cls, session: Session) -> dict[str, object]:
        latest = (
            session.query(BackgroundJob)
            .filter(BackgroundJob.job_type == "daily.forecast_refresh")
            .order_by(BackgroundJob.created_at.desc(), BackgroundJob.id.desc())
            .first()
        )
        if latest is None:
            return {
                "enabled": settings.daily_automation_enabled,
                "max_data_age_days": settings.daily_automation_max_data_age_days,
                "last_job": None,
                "last_successful_ingestion_date": cls(session).latest_successful_actual_date().isoformat()
                if cls(session).latest_successful_actual_date()
                else None,
            }
        payload = latest.payload or {}
        notification_outcomes: list[dict[str, object]] = []
        for event in payload.get("notification_events", []):
            if not isinstance(event, dict) or not event.get("event_type") or not event.get("event_key"):
                continue
            current = NotificationService(session).notification_status(
                str(event["event_type"]),
                str(event["event_key"]),
            )
            notification_outcomes.append({"atm_id": event.get("atm_id"), **current})
        return {
            "enabled": settings.daily_automation_enabled,
            "max_data_age_days": settings.daily_automation_max_data_age_days,
            "last_successful_ingestion_date": payload.get("last_successful_ingestion_date") or (
                cls(session).latest_successful_actual_date().isoformat()
                if cls(session).latest_successful_actual_date()
                else None
            ),
            "notification_status": _notification_summary(notification_outcomes)
            if notification_outcomes
            else payload.get("notification_status", "not_applicable"),
            "notification_outcomes": notification_outcomes or payload.get("notification_outcomes", []),
            "last_job": {
                "job_id": latest.id,
                "status": latest.status,
                "run_status": payload.get("run_status"),
                "operational_date": payload.get("operational_date"),
                "completed_at": latest.completed_at.isoformat() if latest.completed_at else None,
                "last_forecast_run_at": payload.get("last_forecast_run_at"),
                "last_forecast_target_date": payload.get("last_forecast_target_date"),
                "eligible_atms": payload.get("eligible_atms", 0),
                "forecasts_created": payload.get("forecasts_created", 0),
                "skipped_atms": payload.get("skipped_atms", []),
                "failed_atms": payload.get("failed_atms", []),
                "notification_status": _notification_summary(notification_outcomes)
                if notification_outcomes
                else payload.get("notification_status", "not_applicable"),
                "notification_outcomes": notification_outcomes or payload.get("notification_outcomes", []),
                "notification_failures": payload.get("notification_failures", []),
                "last_error": latest.last_error,
            },
        }
