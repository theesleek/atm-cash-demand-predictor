from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.core.permissions import has_permission
from app.data.tinkoff_history import get_prototype_atm_mapping
from app.models.atm import ATM
from app.repositories.atm_repository import ATMRepository
from app.repositories.alert_repository import AlertRepository
from app.repositories.cash_inventory_repository import CashInventoryRepository
from app.repositories.forecast_repository import ForecastRepository
from app.repositories.replenishment_repository import ReplenishmentRepository
from app.services.alert_service import AlertService
from app.services.forecast_service import ForecastService
from app.services.risk_service import CashRiskService
from app.services.ingestion_service import IngestionService


ATM_LIFECYCLE_STATUSES = {"PENDING", "ACTIVE", "INACTIVE", "RETIRED", "active", "inactive", "maintenance", "warning", "critical"}


class ATMService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = ATMRepository(session)
        self.inventory_repository = CashInventoryRepository(session)
        self.forecast_repository = ForecastRepository(session)
        self.alert_service = AlertService(session)
        self.ingestion_service = IngestionService(session)

    @staticmethod
    def _assess_persisted_forecast(forecast, current_cash: float, capacity: float):
        if (
            forecast is None
            or forecast.risk_evaluation_status != "AVAILABLE"
            or forecast.predicted_demand is None
        ):
            return None
        return CashRiskService().assess(current_cash, float(forecast.predicted_demand), capacity)

    @staticmethod
    def _serialize(record: ATM) -> dict[str, object]:
        return {
            "id": record.id,
            "atm_code": record.atm_code,
            "branch_id": record.branch_id,
            "region": record.region,
            "location": record.location,
            "status": record.status,
            "capacity": record.capacity,
            "current_cash": record.current_cash,
            "daily_demand": record.daily_demand,
            "activation_date": record.activation_date.isoformat() if record.activation_date else None,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }

    def create_atm(self, payload: dict[str, object], user_id: int) -> dict[str, object]:
        status = str(payload.get("status") or "PENDING")
        if status not in ATM_LIFECYCLE_STATUSES:
            raise ValueError("Invalid ATM lifecycle status")
        if self.repository.get_by_code(str(payload["atm_code"])) is not None:
            raise ValueError(f"ATM {payload['atm_code']} already exists")
        record = ATM(
            atm_code=str(payload["atm_code"]).strip(),
            location=str(payload.get("location") or "").strip() or None,
            branch_id=str(payload["branch_id"]).strip(),
            region=str(payload["region"]).strip(),
            capacity=float(payload["capacity"]),
            current_cash=0.0,
            daily_demand=0.0,
            status=status,
            activation_date=payload.get("activation_date"),
        )
        self.session.add(record)
        self.session.flush()
        from app.services.audit_service import AuditService
        AuditService(self.session).record(user_id, "ATM_CREATED", "ATM", record.atm_code, "WEB", {"status": status}, commit=False)
        self.session.commit()
        self.session.refresh(record)
        return self._serialize(record)

    def update_atm(self, atm_code: str, payload: dict[str, object], user_id: int) -> dict[str, object] | None:
        record = self.repository.get_by_code(atm_code)
        if record is None:
            return None
        status = payload.get("status")
        if status is not None and str(status) not in ATM_LIFECYCLE_STATUSES:
            raise ValueError("Invalid ATM lifecycle status")
        for field in ("location", "branch_id", "region", "capacity", "status", "activation_date"):
            if field in payload and payload[field] is not None:
                setattr(record, field, payload[field])
        from app.services.audit_service import AuditService
        AuditService(self.session).record(user_id, "ATM_UPDATED", "ATM", record.atm_code, "WEB", {"fields": list(payload)}, commit=False)
        self.session.commit()
        self.session.refresh(record)
        return self._serialize(record)

    def list_atms(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, object]]:
        records = self.repository.list(limit=limit, offset=offset)
        return [
            {
                "id": record.id,
                "atm_code": record.atm_code,
                "branch_id": record.branch_id,
                "region": record.region,
                "location": record.location,
                "status": record.status,
                "capacity": record.capacity,
                "current_cash": record.current_cash,
                "daily_demand": record.daily_demand,
                "activation_date": record.activation_date.isoformat() if record.activation_date else None,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            }
            for record in records
        ]

    def list_network_atms(self, user_id: int, role_name: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, object]]:
        atms = self.repository.list(limit=limit, offset=offset)
        atm_ids = [atm.id for atm in atms]
        forecasts = self.forecast_repository.latest_for_atms(atm_ids)

        latest_replenishments: dict[int, object] = {}
        if has_permission(role_name, "replenishments:read"):
            requested_by = user_id if role_name == "OPERATIONS_OFFICER" else None
            latest_replenishments = ReplenishmentRepository(self.session).latest_for_atms(atm_ids, requested_by)

        result: list[dict[str, object]] = []
        for atm in atms:
            forecast = forecasts.get(atm.id)
            inventory = self.inventory_repository.latest_for_atm(atm.id)
            current_cash = float(inventory.cash_on_hand if inventory is not None else atm.current_cash)
            risk = self._assess_persisted_forecast(
                forecast,
                current_cash,
                float(inventory.capacity if inventory is not None and inventory.capacity > 0 else atm.capacity),
            )
            replenishment = latest_replenishments.get(atm.id)
            result.append(
                {
                    "id": atm.id,
                    "atm_code": atm.atm_code,
                    "branch_id": atm.branch_id,
                    "region": atm.region,
                    "location": f"{atm.branch_id}, {atm.region}",
                    "current_cash": current_cash,
                    "predicted_demand": risk.predicted_demand if risk is not None else None,
                    "predicted_signed_net_cash_flow": float(forecast.predicted_signed_net_cash_flow) if forecast and forecast.predicted_signed_net_cash_flow is not None else None,
                    "forecast_date": forecast.forecast_date.isoformat() if forecast and forecast.forecast_date else None,
                    "projected_cash": risk.projected_cash if risk is not None else None,
                    "risk_level": forecast.risk_level.upper() if forecast and forecast.risk_evaluation_status == "AVAILABLE" and forecast.risk_level else None,
                    "risk_evaluation_status": forecast.risk_evaluation_status if forecast is not None else "NOT_ASSESSED",
                    "risk_evaluation_reason": forecast.risk_evaluation_reason if forecast is not None else None,
                    "last_replenishment_id": replenishment.id if replenishment is not None else None,
                    "last_replenishment_at": replenishment.created_at.isoformat() if replenishment is not None else None,
                    "last_replenishment_status": replenishment.status if replenishment is not None else None,
                    "status": atm.status,
                    "updated_at": atm.updated_at.isoformat() if atm.updated_at else None,
                }
            )
        return result

    def get_atm(self, atm_id: str) -> dict[str, object] | None:
        record = self.repository.get_by_code(atm_id)
        if record is None:
            return None
        return self._serialize(record)

    def get_readiness(self, atm_code: str) -> dict[str, object] | None:
        record = self.repository.get_by_code(atm_code)
        return self.ingestion_service.readiness(record) if record is not None else None

    def get_atm_intelligence(self, atm_code: str, user_id: int, role_name: str) -> dict[str, object] | None:
        atm = self.repository.get_by_code(atm_code)
        if atm is None:
            return None

        inventory = self.inventory_repository.latest_for_atm(atm.id)
        current_cash = float(inventory.cash_on_hand if inventory is not None else atm.current_cash)
        capacity = float(inventory.capacity if inventory is not None and inventory.capacity > 0 else atm.capacity)
        forecast = self.forecast_repository.latest_for_atms([atm.id]).get(atm.id)
        risk = self._assess_persisted_forecast(forecast, current_cash, capacity)

        historical_demand: list[dict[str, object]] = []
        uploaded_history = self.ingestion_service.uploaded_daily_history(atm)
        if uploaded_history is not None:
            rows = uploaded_history.tail(30)
            historical_demand = [
                {"date": row.datetime.date().isoformat(), "demand": float(row.daily_cash_flow)}
                for row in rows.itertuples(index=False)
            ]
        latest_replenishment: dict[int, object] = {}
        if has_permission(role_name, "replenishments:read"):
            requested_by = user_id if role_name == "OPERATIONS_OFFICER" else None
            latest_replenishment = ReplenishmentRepository(self.session).latest_for_atms([atm.id], requested_by)
        replenishment = latest_replenishment.get(atm.id)

        risk_explanation = None
        if risk is not None:
            if risk.risk_level == "NORMAL":
                risk_explanation = (
                    f"Projected cash ({risk.projected_cash:,.2f}) is above the warning threshold "
                    f"({risk.warning_threshold:,.2f})."
                )
            elif risk.risk_level == "WARNING":
                risk_explanation = (
                    f"Projected cash ({risk.projected_cash:,.2f}) is at or below the warning threshold "
                    f"({risk.warning_threshold:,.2f}) but above the high threshold ({risk.high_threshold:,.2f})."
                )
            elif risk.risk_level == "HIGH":
                risk_explanation = (
                    f"Projected cash ({risk.projected_cash:,.2f}) is at or below the high threshold "
                    f"({risk.high_threshold:,.2f}) but above the critical threshold ({risk.critical_threshold:,.2f})."
                )
            else:
                risk_explanation = (
                    f"Projected cash ({risk.projected_cash:,.2f}) is at or below the critical threshold "
                    f"({risk.critical_threshold:,.2f})."
                )

        return {
            "atm_code": atm.atm_code,
            "branch_id": atm.branch_id,
            "region": atm.region,
            "location": atm.location,
            "status": atm.status,
            "current_cash": risk.current_cash if risk is not None else current_cash,
            "capacity": capacity,
            "predicted_demand": risk.predicted_demand if risk is not None else None,
            "predicted_signed_net_cash_flow": forecast.predicted_signed_net_cash_flow if forecast is not None else None,
            "projected_cash": risk.projected_cash if risk is not None else None,
            "risk_level": risk.risk_level if risk is not None else None,
            "risk_explanation": risk_explanation,
            "warning_threshold": risk.warning_threshold if risk is not None else None,
            "high_threshold": risk.high_threshold if risk is not None else None,
            "critical_threshold": risk.critical_threshold if risk is not None else None,
            "recommended_replenishment": risk.recommended_top_up if risk is not None else None,
            "risk_evaluation_status": forecast.risk_evaluation_status if forecast is not None else "NOT_ASSESSED",
            "risk_evaluation_reason": forecast.risk_evaluation_reason if forecast is not None else None,
            "forecast_date": forecast.forecast_date.isoformat() if forecast and forecast.forecast_date else None,
            "forecast_model_version": forecast.model_version if forecast is not None else None,
            "historical_demand": historical_demand,
            "history_source": "Uploaded operational history" if historical_demand else None,
            "forecast_readiness": self.ingestion_service.readiness(atm),
            "last_replenishment": {
                "id": replenishment.id,
                "status": replenishment.status,
                "requested_amount": replenishment.requested_amount,
                "created_at": replenishment.created_at.isoformat() if replenishment.created_at else None,
            } if replenishment is not None else None,
            "updated_at": atm.updated_at.isoformat() if atm.updated_at else None,
        }

    def get_persisted_forecast(self, forecast_id: int) -> dict[str, object] | None:
        forecast = self.forecast_repository.get(forecast_id)
        if forecast is None:
            return None
        atm = self.repository.get(forecast.atm_id)
        if atm is None:
            return None
        inventory = self.inventory_repository.latest_for_atm(atm.id)
        current_cash = float(inventory.cash_on_hand if inventory is not None else atm.current_cash)
        capacity = float(inventory.capacity if inventory is not None and inventory.capacity > 0 else atm.capacity)
        assessment = self._assess_persisted_forecast(forecast, current_cash, capacity)
        return {
            "forecast_id": forecast.id,
            "atm_id": atm.atm_code,
            "forecast_date": forecast.forecast_date.isoformat() if forecast.forecast_date else None,
            "predicted_demand": assessment.predicted_demand if assessment is not None else None,
            "predicted_signed_net_cash_flow": float(forecast.predicted_signed_net_cash_flow) if forecast.predicted_signed_net_cash_flow is not None else None,
            "projected_cash": assessment.projected_cash if assessment is not None else None,
            "risk_level": forecast.risk_level.upper() if assessment is not None and forecast.risk_level else None,
            "risk_evaluation_status": forecast.risk_evaluation_status,
            "risk_evaluation_reason": forecast.risk_evaluation_reason,
            "warning_threshold": assessment.warning_threshold if assessment is not None else None,
            "high_threshold": assessment.high_threshold if assessment is not None else None,
            "critical_threshold": assessment.critical_threshold if assessment is not None else None,
            "recommended_replenishment": float(forecast.recommended_top_up) if assessment is not None and forecast.recommended_top_up is not None else None,
            "model_version": forecast.model_version,
        }

    def get_forecast(self, atm_id: str) -> dict[str, object]:
        record = self.repository.get_by_code(atm_id)
        if record is None:
            raise ValueError(f"ATM {atm_id} not found")

        inventory = self.inventory_repository.latest_for_atm(record.id)
        current_cash = float(inventory.cash_on_hand if inventory is not None else record.current_cash)
        capacity = float(inventory.capacity if inventory is not None and inventory.capacity > 0 else record.capacity)
        readiness = self.ingestion_service.readiness(record)
        if readiness["status"] != "READY":
            raise ValueError(f"Forecast unavailable: {readiness['reason']}")
        forecast = ForecastService(
            history_frame=self.ingestion_service.uploaded_daily_history(record),
        ).generate_forecast(
            atm_id=record.atm_code,
            current_cash=current_cash,
            daily_demand=float(record.daily_demand),
            capacity=capacity,
        )
        persisted_forecast = self.forecast_repository.create(
            atm_id=record.id,
            predicted_demand=forecast.predicted_demand,
            risk_level=forecast.risk_level,
            recommended_top_up=forecast.recommended_top_up,
            forecast_date=datetime.fromisoformat(forecast.forecast_date),
            model_version=forecast.model_version or "unknown",
            predicted_signed_net_cash_flow=forecast.predicted_signed_net_cash_flow,
            risk_evaluation_status=forecast.risk_evaluation_status,
            risk_evaluation_reason=forecast.risk_evaluation_reason,
        )
        if forecast.risk_level is not None and forecast.projected_cash is not None:
            self.alert_service.create_or_update_risk_alert(
                atm_id=record.id,
                atm_code=record.atm_code,
                forecast_id=persisted_forecast.id,
                severity=forecast.risk_level,
                projected_cash=forecast.projected_cash,
            )
        return {
            "atm_id": forecast.atm_id,
            "forecast_date": forecast.forecast_date,
            "predicted_demand": forecast.predicted_demand,
            "predicted_signed_net_cash_flow": forecast.predicted_signed_net_cash_flow,
            "forecast_label": "signed_net_cash_flow",
            "risk_demand_basis": forecast.predicted_demand,
            "risk_level": forecast.risk_level,
            "risk_evaluation_status": forecast.risk_evaluation_status,
            "risk_evaluation_reason": forecast.risk_evaluation_reason,
            "recommended_top_up": forecast.recommended_top_up,
            "current_cash": forecast.current_cash,
            "capacity": forecast.capacity,
            "target": forecast.target,
            "model_name": forecast.model_name,
            "model_version": forecast.model_version,
            "projected_cash": forecast.projected_cash,
            "warning_threshold": forecast.warning_threshold,
            "high_threshold": forecast.high_threshold,
            "critical_threshold": forecast.critical_threshold,
            "safety_buffer": forecast.safety_buffer,
            "inventory_source": "cash_inventory" if inventory is not None else "atm_record_fallback",
            "forecast_source": forecast.source,
        }

    def get_dashboard_summary(self) -> dict[str, object]:
        records = self.repository.list()
        if not records:
            return {
                "atms_monitored": 0,
                "active_atms": 0,
                "at_risk_atms": 0,
                "critical_atms": 0,
                "open_alerts": 0,
                "pending_replenishments": 0,
                "current_network_cash": 0.0,
                "forecasted_demand": 0.0,
                "critical_alerts": 0,
                "warning_alerts": 0,
                "avg_cash_buffer": 0.0,
                "total_capacity": 0.0,
            }

        critical_alerts = sum(1 for record in records if record.current_cash < record.daily_demand * 0.5)
        warning_alerts = sum(1 for record in records if record.current_cash < record.daily_demand * 0.75)
        avg_cash_buffer = sum(record.capacity - record.current_cash for record in records) / len(records)
        atm_ids = [record.id for record in records]
        forecasts = self.forecast_repository.latest_for_atms(atm_ids)
        current_network_cash = sum(
            float(self.inventory_repository.latest_for_atm(record.id).cash_on_hand)
            if self.inventory_repository.latest_for_atm(record.id) is not None else float(record.current_cash)
            for record in records
        )
        assessed_forecasts = [
            forecast
            for forecast in forecasts.values()
            if forecast.risk_evaluation_status == "AVAILABLE" and forecast.predicted_demand is not None and forecast.risk_level
        ]
        forecasted_demand = sum(float(forecast.predicted_demand) for forecast in assessed_forecasts)
        at_risk_atms = sum(1 for forecast in assessed_forecasts if forecast.risk_level.upper() != "NORMAL")
        critical_atms = sum(1 for forecast in assessed_forecasts if forecast.risk_level.upper() == "CRITICAL")

        return {
            "atms_monitored": len(records),
            "active_atms": sum(1 for record in records if str(record.status).lower() == "active"),
            "at_risk_atms": at_risk_atms,
            "critical_atms": critical_atms,
            "open_alerts": AlertRepository(self.session).count_by_status("OPEN"),
            "pending_replenishments": ReplenishmentRepository(self.session).count_by_status("REQUESTED"),
            "current_network_cash": round(float(current_network_cash), 2),
            "forecasted_demand": round(float(forecasted_demand), 2),
            "critical_alerts": critical_alerts,
            "warning_alerts": warning_alerts,
            "avg_cash_buffer": round(float(avg_cash_buffer), 2),
            "total_capacity": round(float(sum(record.capacity for record in records)), 2),
        }
