from __future__ import annotations

from dataclasses import dataclass

from app.data.tinkoff_history import build_feature_row_from_history, get_prototype_atm_mapping
from app.ml.inference import ProductionInferenceService
from app.services.risk_service import CashRiskService


@dataclass
class ForecastResult:
    atm_id: str
    predicted_demand: float
    predicted_signed_net_cash_flow: float
    risk_level: str
    recommended_top_up: float
    current_cash: float
    capacity: float
    forecast_date: str
    target: str
    model_name: str
    model_version: str | None
    projected_cash: float
    warning_threshold: float
    high_threshold: float
    critical_threshold: float
    safety_buffer: float
    source: str


class ForecastService:
    def __init__(
        self,
        inference_service: ProductionInferenceService | None = None,
        risk_service: CashRiskService | None = None,
        history_frame=None,
    ):
        self.inference_service = inference_service or ProductionInferenceService()
        self.risk_service = risk_service or CashRiskService()
        self.history_frame = history_frame

    def generate_forecast(self, atm_id: str, current_cash: float, daily_demand: float, capacity: float) -> ForecastResult:
        if self.history_frame is None:
            raise ValueError("Forecast unavailable: uploaded operational history is required.")
        mapping = get_prototype_atm_mapping()
        if atm_id not in mapping:
            raise ValueError("Forecast unavailable: production model requires a compatible ATM identity mapping; retraining is required.")
        feature_frame, forecast_date = build_feature_row_from_history(
            atm_id,
            self.inference_service.feature_names,
            self.history_frame,
            mapping[atm_id],
        )
        inference_result = self.inference_service.predict(feature_frame)
        risk = self.risk_service.assess(current_cash, inference_result.prediction, capacity)

        return ForecastResult(
            atm_id=atm_id,
            predicted_demand=risk.predicted_demand,
            predicted_signed_net_cash_flow=round(float(inference_result.prediction), 2),
            risk_level=risk.risk_level,
            recommended_top_up=risk.recommended_top_up,
            current_cash=risk.current_cash,
            capacity=capacity,
            forecast_date=forecast_date,
            target=inference_result.target,
            model_name=inference_result.model_name,
            model_version=inference_result.model_version,
            projected_cash=risk.projected_cash,
            warning_threshold=risk.warning_threshold,
            high_threshold=risk.high_threshold,
            critical_threshold=risk.critical_threshold,
            safety_buffer=risk.safety_buffer,
            source="uploaded_dataset",
        )
