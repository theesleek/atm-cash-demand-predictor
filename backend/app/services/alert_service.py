from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.orm import Session

from app.models.atm import Alert
from app.repositories.alert_repository import AlertRepository
from app.repositories.atm_repository import ATMRepository
from app.realtime import publish_realtime_event
from app.services.audit_service import AuditService


AlertSource = Literal["SYSTEM", "WEB", "API", "TELEGRAM"]
AlertStatus = Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"]
RISK_SEVERITIES = {"WARNING", "HIGH", "CRITICAL"}


class AlertNotFoundError(LookupError):
    pass


class AlertStateError(ValueError):
    pass


class AlertService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = AlertRepository(session)
        self.atm_repository = ATMRepository(session)
        self.audit_service = AuditService(session)

    def create_or_update_risk_alert(
        self,
        atm_id: int,
        atm_code: str,
        forecast_id: int,
        severity: str,
        projected_cash: float,
    ) -> Alert | None:
        normalized_severity = severity.upper()
        if normalized_severity == "NORMAL":
            return None
        if normalized_severity not in RISK_SEVERITIES:
            raise ValueError(f"Unsupported risk severity: {severity}")

        message = f"{normalized_severity} cash risk for {atm_code}: projected cash is {projected_cash:.2f}."
        is_new_alert = self.repository.get_active_risk_alert(atm_id, normalized_severity) is None
        notification_required = is_new_alert and normalized_severity in {"HIGH", "CRITICAL"}
        async_notification = False
        if notification_required:
            from app.core.config import settings

            async_notification = settings.async_notifications

        alert = self.repository.upsert_risk_alert(
            atm_id=atm_id,
            forecast_id=forecast_id,
            severity=normalized_severity,
            message=message,
            action_source="SYSTEM",
            commit=not (notification_required and async_notification),
        )
        if notification_required:
            from app.services.notification_service import NotificationService
            from app.core.config import settings

            service = NotificationService(self.repository.session)
            event = f"RISK_{normalized_severity}"
            if settings.async_notifications:
                service.stage_notification(
                    f"{event}:{alert.id}",
                    event,
                    f"{normalized_severity} cash risk: {atm_code}",
                    message,
                )
                self.repository.session.commit()
            else:
                service.notify(
                    event,
                    f"{normalized_severity} cash risk: {atm_code}",
                    message,
                    event_key=f"{event}:{alert.id}",
                )
        if is_new_alert:
            publish_realtime_event(
                "alert.created",
                "ALERT",
                alert.id,
                atm_id=atm_code,
                status=alert.status,
                severity=alert.severity,
                source="SYSTEM",
            )
        self.audit_service.record(
            user_id=None,
            action="RISK_ALERT_UPSERTED",
            entity_type="ALERT",
            entity_id=alert.id,
            source="SYSTEM",
            metadata={"severity": normalized_severity, "forecast_id": forecast_id},
        )
        return alert

    def list_alerts(self, atm_code: str | None = None, status: str | None = None, *, limit: int = 100, offset: int = 0) -> list[dict[str, object]]:
        atm_id = None
        if atm_code is not None:
            atm = self.atm_repository.get_by_code(atm_code)
            if atm is None:
                return []
            atm_id = atm.id
        normalized_status = status.upper() if status else None
        if normalized_status and normalized_status not in {"OPEN", "ACKNOWLEDGED", "RESOLVED"}:
            raise ValueError(f"Unsupported alert status: {status}")
        return [self._serialize(alert) for alert in self.repository.list(atm_id, normalized_status, limit=limit, offset=offset)]

    def get_alert(self, alert_id: int) -> dict[str, object]:
        alert = self.repository.get(alert_id)
        if alert is None:
            raise AlertNotFoundError(f"Alert {alert_id} not found")
        return self._serialize(alert)

    def acknowledge(
        self,
        alert_id: int,
        actor: str,
        source: AlertSource,
        user_id: int | None = None,
    ) -> dict[str, object]:
        alert = self._get_for_transition(alert_id)
        if alert.status != "OPEN":
            raise AlertStateError(f"Alert {alert_id} cannot be acknowledged from status {alert.status}")
        alert.status = "ACKNOWLEDGED"
        alert.acknowledged_by = actor
        alert.acknowledged_at = datetime.now(timezone.utc)
        alert.action_source = source
        saved_alert = self.repository.save(alert, commit=False)
        self.audit_service.record(user_id, "ALERT_ACKNOWLEDGED", "ALERT", alert.id, source, commit=False)
        self._commit()
        publish_realtime_event(
            "alert.acknowledged",
            "ALERT",
            alert.id,
            atm_id=alert.atm.atm_code,
            status=alert.status,
            severity=alert.severity,
            source=source,
        )
        return self._serialize(saved_alert)

    def resolve(
        self,
        alert_id: int,
        actor: str,
        source: AlertSource,
        user_id: int | None = None,
    ) -> dict[str, object]:
        alert = self._get_for_transition(alert_id)
        if alert.status not in {"OPEN", "ACKNOWLEDGED"}:
            raise AlertStateError(f"Alert {alert_id} cannot be resolved from status {alert.status}")
        alert.status = "RESOLVED"
        alert.resolved_by = actor
        alert.resolved_at = datetime.now(timezone.utc)
        alert.action_source = source
        saved_alert = self.repository.save(alert, commit=False)
        self.audit_service.record(user_id, "ALERT_RESOLVED", "ALERT", alert.id, source, commit=False)
        self._commit()
        publish_realtime_event(
            "alert.resolved",
            "ALERT",
            alert.id,
            atm_id=alert.atm.atm_code,
            status=alert.status,
            severity=alert.severity,
            source=source,
        )
        return self._serialize(saved_alert)

    def _get_for_transition(self, alert_id: int) -> Alert:
        alert = self.repository.get_for_update(alert_id)
        if alert is None:
            raise AlertNotFoundError(f"Alert {alert_id} not found")
        return alert

    def _commit(self) -> None:
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    @staticmethod
    def _serialize(alert: Alert) -> dict[str, object]:
        return {
            "alert_id": alert.id,
            "atm_id": alert.atm.atm_code,
            "forecast_id": alert.forecast_id,
            "severity": alert.severity,
            "alert_type": alert.alert_type,
            "message": alert.message,
            "status": alert.status,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
            "acknowledged_by": alert.acknowledged_by,
            "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
            "resolved_by": alert.resolved_by,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "action_source": alert.action_source,
        }
