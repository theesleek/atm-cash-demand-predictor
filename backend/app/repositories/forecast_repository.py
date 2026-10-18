from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.atm import Forecast


class ForecastRepository:
    def __init__(self, session: Session):
        self.session = session

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
        predicted_demand: float,
        risk_level: str,
        recommended_top_up: float,
        forecast_date: datetime,
        model_version: str,
    ) -> Forecast:
        item = Forecast(
            atm_id=atm_id,
            forecast_date=forecast_date,
            predicted_demand=predicted_demand,
            risk_level=risk_level,
            recommended_top_up=recommended_top_up,
            model_version=model_version,
        )
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item
