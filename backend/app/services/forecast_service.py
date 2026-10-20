from __future__ import annotations

from dataclasses import dataclass

from app.data.tinkoff_history import build_feature_row_from_history, get_prototype_atm_mapping
from app.ml.inference import ProductionInferenceService
from app.models.atm import FORECAST_TYPE_SIGNED_FLOW, FORECAST_TYPE_WITHDRAWAL_DEMAND
from app.services.risk_service import CashRiskService


RISK_UNAVAILABLE = "UNAVAILABLE"
RISK_AVAILABLE = "AVAILABLE"
RISK_UNAVAILABLE_REASON = "Verified withdrawal-demand data is required for demand-based risk evaluation."
_FORECAST_TYPE_BY_TARGET = {
    "next_day_cash_flow": FORECAST_TYPE_SIGNED_FLOW,
    "withdrawal_demand": FORECAST_TYPE_WITHDRAWAL_DEMAND,
    "next_day_withdrawal_demand": FORECAST_TYPE_WITHDRAWAL_DEMAND,
}


def forecast_type_for_target(target: str) -> str:
    try:
        return _FORECAST_TYPE_BY_TARGET[target]
    except KeyError as exc:
        raise ValueError(f"Unsupported forecast target: {target}") from exc


@dataclass
class ForecastResult:
    atm_id: str
    predicted_demand: float | None
    predicted_signed_net_cash_flow: float | None
    risk_level: str | None
    recommended_top_up: float | None
    current_cash: float
    capacity: float
    forecast_date: str
    target: str
    model_name: str
    model_version: str | None
    projected_cash: float | None
    warning_threshold: float | None
    high_threshold: float | None
    critical_threshold: float | None
    safety_buffer: float | None
    risk_evaluation_status: str
    risk_evaluation_reason: str | None
    source: str
    forecast_type: str | None = None

    def __post_init__(self) -> None:
        if self.forecast_type is None:
            self.forecast_type = forecast_type_for_target(self.target)
        if self.forecast_type not in {FORECAST_TYPE_SIGNED_FLOW, FORECAST_TYPE_WITHDRAWAL_DEMAND}:
            raise ValueError(f"Unsupported forecast type: {self.forecast_type}")


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
        forecast_type = forecast_type_for_target(inference_result.target)
        risk = None if forecast_type == FORECAST_TYPE_SIGNED_FLOW else self.risk_service.assess(
            current_cash,
            inference_result.prediction,
            capacity,
        )

        return ForecastResult(
            atm_id=atm_id,
            predicted_demand=risk.predicted_demand if risk is not None else None,
            predicted_signed_net_cash_flow=(
                round(float(inference_result.prediction), 2)
                if forecast_type == FORECAST_TYPE_SIGNED_FLOW
                else None
            ),
            risk_level=risk.risk_level if risk is not None else None,
            recommended_top_up=risk.recommended_top_up if risk is not None else None,
            current_cash=risk.current_cash if risk is not None else round(max(float(current_cash), 0.0), 2),
            capacity=capacity,
            forecast_date=forecast_date,
            target=inference_result.target,
            model_name=inference_result.model_name,
            model_version=inference_result.model_version,
            projected_cash=risk.projected_cash if risk is not None else None,
            warning_threshold=risk.warning_threshold if risk is not None else None,
            high_threshold=risk.high_threshold if risk is not None else None,
            critical_threshold=risk.critical_threshold if risk is not None else None,
            safety_buffer=risk.safety_buffer if risk is not None else None,
            risk_evaluation_status=RISK_AVAILABLE if risk is not None else RISK_UNAVAILABLE,
            risk_evaluation_reason=None if risk is not None else RISK_UNAVAILABLE_REASON,
            source="uploaded_dataset",
            forecast_type=forecast_type,
        )
