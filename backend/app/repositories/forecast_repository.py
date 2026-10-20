from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.atm import Forecast


class ForecastRepository:
    FORECAST_IDENTITY_CONSTRAINT = "uq_forecasts_atm_date_model"

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _require_forecast_date(forecast_date: datetime | None) -> datetime:
        if forecast_date is None:
            raise ValueError("forecast_date is required")
        return forecast_date

    def list_for_atm(self, atm_id: int) -> list[Forecast]:
        return self.session.query(Forecast).filter(Forecast.atm_id == atm_id).order_by(Forecast.forecast_date.desc()).all()

    def get(self, forecast_id: int) -> Forecast | None:
        return self.session.get(Forecast, forecast_id)

    def latest_for_atms(self, atm_ids: list[int]) -> dict[int, Forecast]:
        if not atm_ids:
            return {}
        forecasts = (
            self.session.query(Forecast)
            .filter(Forecast.atm_id.in_(atm_ids))
            .order_by(Forecast.id.desc())
            .all()
        )
        latest: dict[int, Forecast] = {}
        for forecast in forecasts:
            latest.setdefault(forecast.atm_id, forecast)
        return latest

    def create(
        self,
        atm_id: int,
        predicted_demand: float | None,
        risk_level: str | None,
        recommended_top_up: float | None,
        forecast_date: datetime,
        model_version: str,
        predicted_signed_net_cash_flow: float | None = None,
        risk_evaluation_status: str = "AVAILABLE",
        risk_evaluation_reason: str | None = None,
    ) -> Forecast:
        item, _created = self.get_or_create(
            atm_id=atm_id,
            predicted_demand=predicted_demand,
            risk_level=risk_level,
            recommended_top_up=recommended_top_up,
            forecast_date=forecast_date,
            model_version=model_version,
            predicted_signed_net_cash_flow=predicted_signed_net_cash_flow,
            risk_evaluation_status=risk_evaluation_status,
            risk_evaluation_reason=risk_evaluation_reason,
        )
        return item

    def get_or_create(
        self,
        atm_id: int,
        predicted_demand: float | None,
        risk_level: str | None,
        recommended_top_up: float | None,
        forecast_date: datetime,
        model_version: str,
        predicted_signed_net_cash_flow: float | None = None,
        risk_evaluation_status: str = "AVAILABLE",
        risk_evaluation_reason: str | None = None,
    ) -> tuple[Forecast, bool]:
        forecast_date = self._require_forecast_date(forecast_date)
        existing = (
            self.session.query(Forecast)
            .filter(
                Forecast.atm_id == atm_id,
                Forecast.forecast_date == forecast_date,
                Forecast.model_version == model_version,
            )
            .one_or_none()
        )
        if existing is not None:
            return existing, False
        item = Forecast(
            atm_id=atm_id,
            forecast_date=forecast_date,
            predicted_demand=predicted_demand,
            predicted_signed_net_cash_flow=predicted_signed_net_cash_flow,
            risk_level=risk_level,
            risk_evaluation_status=risk_evaluation_status,
            risk_evaluation_reason=risk_evaluation_reason,
            recommended_top_up=recommended_top_up,
            model_version=model_version,
        )
        self.session.add(item)
        try:
            self.session.commit()
        except IntegrityError as exc:
            if not self._is_forecast_identity_conflict(exc):
                self.session.rollback()
                raise
            self.session.rollback()
            existing = (
                self.session.query(Forecast)
                .filter(
                    Forecast.atm_id == atm_id,
                    Forecast.forecast_date == forecast_date,
                    Forecast.model_version == model_version,
                )
                .one_or_none()
            )
            if existing is None:
                raise
            return existing, False
        self.session.refresh(item)
        return item, True

    @classmethod
    def _is_forecast_identity_conflict(cls, error: IntegrityError) -> bool:
        """Return true only for the forecast identity uniqueness violation."""
        original = error.orig
        sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
        constraint_name = getattr(getattr(original, "diag", None), "constraint_name", None)
        if sqlstate == "23505" and constraint_name == cls.FORECAST_IDENTITY_CONSTRAINT:
            return True

        sqlite_error_name = getattr(original, "sqlite_errorname", None)
        message = str(original).lower()
        return bool(
            sqlite_error_name == "SQLITE_CONSTRAINT_UNIQUE"
            and (
                cls.FORECAST_IDENTITY_CONSTRAINT.lower() in message
                or all(column in message for column in ("atm_id", "forecast_date", "model_version"))
            )
        )
