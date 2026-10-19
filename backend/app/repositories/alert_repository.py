from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.atm import Alert


class AlertRepository:
    ACTIVE_STATUSES = ("OPEN", "ACKNOWLEDGED")

    def __init__(self, session: Session):
        self.session = session

    def count_by_status(self, status: str) -> int:
        return self.session.query(func.count(Alert.id)).filter(Alert.status == status).scalar() or 0

    def list_recent(self, limit: int = 20) -> list[Alert]:
        return self.session.query(Alert).order_by(Alert.created_at.desc()).limit(limit).all()

    def list(self, atm_id: int | None = None, status: str | None = None, *, limit: int = 100, offset: int = 0) -> list[Alert]:
        query = self.session.query(Alert)
        if atm_id is not None:
            query = query.filter(Alert.atm_id == atm_id)
        if status is not None:
            query = query.filter(Alert.status == status)
        return query.order_by(Alert.created_at.desc(), Alert.id.desc()).offset(offset).limit(limit).all()

    def get(self, alert_id: int) -> Alert | None:
        return self.session.query(Alert).filter(Alert.id == alert_id).first()

    def get_for_update(self, alert_id: int) -> Alert | None:
        return self.session.query(Alert).filter(Alert.id == alert_id).with_for_update().first()

    def get_active_risk_alert(self, atm_id: int, severity: str) -> Alert | None:
        return (
            self.session.query(Alert)
            .filter(
                Alert.atm_id == atm_id,
                Alert.alert_type == "CASH_RISK",
                Alert.severity == severity,
                Alert.status.in_(self.ACTIVE_STATUSES),
            )
            .order_by(Alert.created_at.desc(), Alert.id.desc())
            .first()
        )

    def upsert_risk_alert(
        self,
        atm_id: int,
        forecast_id: int,
        severity: str,
        message: str,
        action_source: str = "SYSTEM",
        *,
        commit: bool = True,
    ) -> Alert:
        alert = (
            self.session.query(Alert)
            .filter(
                Alert.atm_id == atm_id,
                Alert.alert_type == "CASH_RISK",
                Alert.severity == severity,
                Alert.status.in_(self.ACTIVE_STATUSES),
            )
            .order_by(Alert.created_at.desc(), Alert.id.desc())
            .first()
        )
        if alert is None:
            alert = Alert(
                atm_id=atm_id,
                forecast_id=forecast_id,
                alert_type="CASH_RISK",
                severity=severity,
                status="OPEN",
                message=message,
                action_source=action_source,
            )
            self.session.add(alert)
        else:
            alert.forecast_id = forecast_id
            alert.message = message
            alert.action_source = action_source
        try:
            if commit:
                self.session.commit()
            else:
                self.session.flush()
        except IntegrityError:
            self.session.rollback()
            alert = (
                self.session.query(Alert)
                .filter(
                    Alert.atm_id == atm_id,
                    Alert.alert_type == "CASH_RISK",
                    Alert.severity == severity,
                    Alert.status.in_(self.ACTIVE_STATUSES),
                )
                .order_by(Alert.created_at.desc(), Alert.id.desc())
                .first()
            )
            if alert is None:
                raise
            alert.forecast_id = forecast_id
            alert.message = message
            alert.action_source = action_source
            if commit:
                self.session.commit()
            else:
                self.session.flush()
        self.session.refresh(alert)
        return alert

    def save(self, alert: Alert, *, commit: bool = True) -> Alert:
        self.session.add(alert)
        if commit:
            try:
                self.session.commit()
            except SQLAlchemyError:
                self.session.rollback()
                raise
        else:
            self.session.flush()
        self.session.refresh(alert)
        return alert
