from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class RiskResult:
    current_cash: float
    predicted_demand: float
    projected_cash: float
    warning_threshold: float
    high_threshold: float
    critical_threshold: float
    safety_buffer: float
    risk_level: str
    recommended_top_up: float


class CashRiskService:
    """Thresholds and safety buffer are multiples of predicted daily demand."""

    def __init__(
        self,
        warning_threshold: float | None = None,
        high_threshold: float | None = None,
        critical_threshold: float | None = None,
        safety_buffer: float | None = None,
    ):
        self.warning_threshold = warning_threshold if warning_threshold is not None else settings.risk_warning_threshold
        self.high_threshold = high_threshold if high_threshold is not None else settings.risk_high_threshold
        self.critical_threshold = critical_threshold if critical_threshold is not None else settings.risk_critical_threshold
        self.safety_buffer = safety_buffer if safety_buffer is not None else settings.risk_safety_buffer
        if not (self.warning_threshold >= self.high_threshold >= self.critical_threshold >= 0):
            raise ValueError("Risk thresholds must satisfy warning >= high >= critical >= 0")
        if self.safety_buffer < 0:
            raise ValueError("Safety buffer cannot be negative")

    def assess(self, current_cash: float, predicted_demand: float, capacity: float) -> RiskResult:
        if capacity < 0:
            raise ValueError("ATM capacity cannot be negative")

        demand = float(predicted_demand)
        if demand < 0:
            raise ValueError("Risk assessment requires a nonnegative verified withdrawal-demand value")
        cash = max(float(current_cash), 0.0)
        projected_cash = max(cash - demand, 0.0)
        warning_amount = demand * self.warning_threshold
        high_amount = demand * self.high_threshold
        critical_amount = demand * self.critical_threshold

        if projected_cash <= critical_amount:
            risk_level = "CRITICAL"
        elif projected_cash <= high_amount:
            risk_level = "HIGH"
        elif projected_cash <= warning_amount:
            risk_level = "WARNING"
        else:
            risk_level = "NORMAL"

        safety_amount = demand * self.safety_buffer
        desired_cash = demand + safety_amount
        needed = max(desired_cash - projected_cash, 0.0)
        capacity_headroom = max(float(capacity) - projected_cash, 0.0)
        recommended_top_up = min(needed, capacity_headroom)

        return RiskResult(
            current_cash=round(cash, 2),
            predicted_demand=round(demand, 2),
            projected_cash=round(projected_cash, 2),
            warning_threshold=round(warning_amount, 2),
            high_threshold=round(high_amount, 2),
            critical_threshold=round(critical_amount, 2),
            safety_buffer=round(safety_amount, 2),
            risk_level=risk_level,
            recommended_top_up=round(max(recommended_top_up, 0.0), 2),
        )
