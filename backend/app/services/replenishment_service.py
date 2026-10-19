from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth import User
from app.models.replenishment import Replenishment
from app.repositories.cash_inventory_repository import CashInventoryRepository
from app.repositories.replenishment_repository import ReplenishmentRepository
from app.realtime import publish_realtime_event
from app.services.audit_service import AuditService


ActionSource = Literal["WEB", "API"]


class ReplenishmentNotFoundError(LookupError):
    pass


class ReplenishmentStateError(ValueError):
    pass


class ReplenishmentValidationError(ValueError):
    pass


class ReplenishmentAccessError(PermissionError):
    pass


class ReplenishmentService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = ReplenishmentRepository(session)
        self.inventory_repository = CashInventoryRepository(session)
        self.audit = AuditService(session)

    def _notify(
        self,
        event_type: str,
        replenishment: Replenishment,
        detail: str = "",
        *,
        stage: bool = False,
    ) -> None:
        from app.services.notification_service import NotificationService
        from app.core.config import settings

        message = (
            f"ATM {replenishment.atm.atm_code}; replenishment #{replenishment.id}; "
            f"status {replenishment.status}; requested amount {replenishment.requested_amount:.2f}."
        )
        if detail:
            message = f"{message} {detail}"
        service = NotificationService(self.session)
        event = f"REPLENISHMENT_{event_type}"
        event_key = f"{event}:{replenishment.id}"
        if stage:
            service.stage_notification(
                event_key,
                event,
                f"Replenishment {event_type.lower()}",
                message,
            )
        else:
            service.notify(
                event,
                f"Replenishment {event_type.lower()}",
                message,
                event_key=event_key,
            )

    def _publish(self, event_type: str, replenishment: Replenishment, source: ActionSource) -> None:
        publish_realtime_event(
            f"replenishment.{event_type.lower()}",
            "REPLENISHMENT",
            replenishment.id,
            atm_id=replenishment.atm.atm_code,
            status=replenishment.status,
            source=source,
        )

    def create(
        self,
        actor: User,
        atm_code: str,
        requested_amount: float | None,
        forecast_id: int | None,
        submit: bool,
        notes: str | None,
        source: ActionSource,
    ) -> dict[str, object]:
        atm = self.repository.get_atm(atm_code)
        if atm is None:
            raise ReplenishmentNotFoundError(f"ATM {atm_code} not found")

        forecast = self.repository.get_forecast(forecast_id) if forecast_id is not None else None
        if forecast_id is not None and forecast is None:
            raise ReplenishmentNotFoundError(f"Forecast {forecast_id} not found")
        if forecast is not None and forecast.atm_id != atm.id:
            raise ReplenishmentValidationError("Forecast does not belong to the requested ATM")
        if forecast is None:
            forecast = self.repository.latest_forecast_for_atm(atm.id)

        amount = requested_amount
        if amount is None and forecast is not None:
            amount = float(forecast.recommended_top_up)
        if amount is None or amount <= 0:
            raise ReplenishmentValidationError("A positive requested amount or forecast recommendation is required")

        capacity = self._capacity(atm.id, float(atm.capacity))
        if amount > capacity:
            raise ReplenishmentValidationError("Requested amount cannot exceed ATM cash capacity")

        replenishment = Replenishment(
            atm_id=atm.id,
            forecast_id=forecast.id if forecast is not None else None,
            requested_amount=amount,
            status="REQUESTED" if submit else "DRAFT",
            requested_by=actor.id,
            notes=notes,
        )
        saved = self.repository.create(replenishment, commit=False)
        self._audit(actor.id, "REPLENISHMENT_CREATED", saved, source, {"status": saved.status}, commit=False)
        if saved.status == "REQUESTED" and settings.async_notifications:
            self._notify("REQUESTED", saved, stage=True)
        self._commit()
        if saved.status == "REQUESTED" and not settings.async_notifications:
            self._notify("REQUESTED", saved)
        if saved.status == "REQUESTED":
            self._publish("REQUESTED", saved, source)
        return self._serialize(saved)

    def submit(self, replenishment_id: int, actor: User, source: ActionSource) -> dict[str, object]:
        replenishment = self._get_accessible(replenishment_id, actor, for_update=True)
        if replenishment.status != "DRAFT":
            raise ReplenishmentStateError("Only draft requests can be submitted")
        replenishment.status = "REQUESTED"
        saved = self.repository.save(replenishment, commit=False)
        self._audit(actor.id, "REPLENISHMENT_REQUESTED", saved, source, commit=False)
        if settings.async_notifications:
            self._notify("REQUESTED", saved, stage=True)
        self._commit()
        if not settings.async_notifications:
            self._notify("REQUESTED", saved)
        self._publish("REQUESTED", saved, source)
        return self._serialize(saved)

    def list_for_user(self, actor: User, status: str | None = None, *, limit: int = 100, offset: int = 0) -> list[dict[str, object]]:
        normalized_status = status.upper() if status else None
        if normalized_status and normalized_status not in REPLENISHMENT_STATUS_VALUES:
            raise ReplenishmentValidationError(f"Invalid replenishment status: {status}")
        rows = self.repository.list_for_user(actor.id, actor.role.name, normalized_status, limit=limit, offset=offset)
        return [self._serialize(item) for item in rows]

    def get(self, replenishment_id: int, actor: User) -> dict[str, object]:
        return self._serialize(self._get_accessible(replenishment_id, actor))

    def get_audit_history(self, replenishment_id: int, actor: User) -> list[dict[str, object]]:
        self._get_accessible(replenishment_id, actor)
        return AuditService(self.session).list_for_entity("REPLENISHMENT", replenishment_id)

    def approve(
        self,
        replenishment_id: int,
        actor: User,
        approved_amount: float | None,
        notes: str | None,
        source: ActionSource,
    ) -> dict[str, object]:
        replenishment = self._get_accessible(replenishment_id, actor, for_update=True)
        if replenishment.status != "REQUESTED":
            raise ReplenishmentStateError("Only requested replenishments can be approved")
        amount = float(approved_amount if approved_amount is not None else replenishment.requested_amount)
        if amount <= 0:
            raise ReplenishmentValidationError("Approved amount must be positive")
        atm = self.repository.get_atm_by_id(replenishment.atm_id)
        if atm is None:
            raise ReplenishmentNotFoundError("ATM for replenishment no longer exists")
        capacity = self._capacity(atm.id, float(atm.capacity))
        if amount > capacity:
            raise ReplenishmentValidationError("Approved amount cannot exceed ATM cash capacity")

        replenishment.approved_amount = amount
        replenishment.approved_by = actor.id
        replenishment.approved_at = datetime.now(timezone.utc)
        replenishment.status = "APPROVED"
        if notes:
            replenishment.notes = notes
        saved = self.repository.save(replenishment, commit=False)
        self._audit(actor.id, "REPLENISHMENT_APPROVED", saved, source, {"approved_amount": amount}, commit=False)
        if settings.async_notifications:
            self._notify("APPROVED", saved, f"Approved amount {amount:.2f}.", stage=True)
        self._commit()
        if not settings.async_notifications:
            self._notify("APPROVED", saved, f"Approved amount {amount:.2f}.")
        self._publish("APPROVED", saved, source)
        return self._serialize(saved)

    def reject(self, replenishment_id: int, actor: User, reason: str, source: ActionSource) -> dict[str, object]:
        replenishment = self._get_accessible(replenishment_id, actor, for_update=True)
        if replenishment.status != "REQUESTED":
            raise ReplenishmentStateError("Only requested replenishments can be rejected")
        replenishment.status = "REJECTED"
        replenishment.reason = reason
        saved = self.repository.save(replenishment, commit=False)
        self._audit(actor.id, "REPLENISHMENT_REJECTED", saved, source, {"reason": reason}, commit=False)
        if settings.async_notifications:
            self._notify("REJECTED", saved, f"Reason: {reason}", stage=True)
        self._commit()
        if not settings.async_notifications:
            self._notify("REJECTED", saved, f"Reason: {reason}")
        self._publish("REJECTED", saved, source)
        return self._serialize(saved)

    def schedule(
        self,
        replenishment_id: int,
        actor: User,
        scheduled_at: datetime,
        notes: str | None,
        source: ActionSource,
    ) -> dict[str, object]:
        replenishment = self._get_accessible(replenishment_id, actor, for_update=True)
        if replenishment.status != "APPROVED":
            raise ReplenishmentStateError("Only approved replenishments can be scheduled")
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        replenishment.status = "SCHEDULED"
        replenishment.scheduled_at = scheduled_at
        if notes:
            replenishment.notes = notes
        saved = self.repository.save(replenishment, commit=False)
        self._audit(actor.id, "REPLENISHMENT_SCHEDULED", saved, source, {"scheduled_at": scheduled_at.isoformat()}, commit=False)
        self._commit()
        self._publish("SCHEDULED", saved, source)
        return self._serialize(saved)

    def complete(
        self,
        replenishment_id: int,
        actor: User,
        notes: str | None,
        source: ActionSource,
    ) -> dict[str, object]:
        replenishment = self._get_accessible(replenishment_id, actor, for_update=True)
        if replenishment.status != "SCHEDULED":
            raise ReplenishmentStateError("Only scheduled replenishments can be completed")
        replenishment.status = "COMPLETED"
        replenishment.completed_at = datetime.now(timezone.utc)
        if notes:
            replenishment.notes = notes
        saved = self.repository.save(replenishment, commit=False)
        self._audit(actor.id, "REPLENISHMENT_COMPLETED", saved, source, commit=False)
        if settings.async_notifications:
            self._notify("COMPLETED", saved, stage=True)
        self._commit()
        if not settings.async_notifications:
            self._notify("COMPLETED", saved)
        self._publish("COMPLETED", saved, source)
        return self._serialize(saved)

    def cancel(self, replenishment_id: int, actor: User, source: ActionSource) -> dict[str, object]:
        replenishment = self._get_accessible(replenishment_id, actor, for_update=True)
        if replenishment.status not in {"DRAFT", "REQUESTED"}:
            raise ReplenishmentStateError("Only draft or requested replenishments can be cancelled")
        replenishment.status = "CANCELLED"
        saved = self.repository.save(replenishment, commit=False)
        self._audit(actor.id, "REPLENISHMENT_CANCELLED", saved, source, commit=False)
        self._commit()
        return self._serialize(saved)

    def _get_accessible(self, replenishment_id: int, actor: User, *, for_update: bool = False) -> Replenishment:
        replenishment = self.repository.get_for_update(replenishment_id) if for_update else self.repository.get(replenishment_id)
        if replenishment is None:
            raise ReplenishmentNotFoundError(f"Replenishment {replenishment_id} not found")
        if actor.role.name == "OPERATIONS_OFFICER" and replenishment.requested_by != actor.id:
            raise ReplenishmentNotFoundError(f"Replenishment {replenishment_id} not found")
        return replenishment

    def _capacity(self, atm_id: int, atm_capacity: float) -> float:
        inventory = self.inventory_repository.latest_for_atm(atm_id)
        if inventory is not None and inventory.capacity > 0:
            return float(inventory.capacity)
        return atm_capacity

    def _audit(
        self,
        actor_id: int,
        action: str,
        replenishment: Replenishment,
        source: ActionSource,
        metadata: dict[str, object] | None = None,
        *,
        commit: bool = True,
    ) -> None:
        self.audit.record(
            actor_id,
            action,
            "REPLENISHMENT",
            replenishment.id,
            source,
            metadata,
            commit=commit,
        )

    def _commit(self) -> None:
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    @staticmethod
    def _serialize(replenishment: Replenishment) -> dict[str, object]:
        return {
            "replenishment_id": replenishment.id,
            "atm_id": replenishment.atm.atm_code,
            "forecast_id": replenishment.forecast_id,
            "requested_amount": replenishment.requested_amount,
            "approved_amount": replenishment.approved_amount,
            "status": replenishment.status,
            "requested_by": replenishment.requested_by,
            "approved_by": replenishment.approved_by,
            "scheduled_at": replenishment.scheduled_at.isoformat() if replenishment.scheduled_at else None,
            "approved_at": replenishment.approved_at.isoformat() if replenishment.approved_at else None,
            "completed_at": replenishment.completed_at.isoformat() if replenishment.completed_at else None,
            "created_at": replenishment.created_at.isoformat() if replenishment.created_at else None,
            "updated_at": replenishment.updated_at.isoformat() if replenishment.updated_at else None,
            "notes": replenishment.notes,
            "reason": replenishment.reason,
        }


REPLENISHMENT_STATUS_VALUES = frozenset(
    {"DRAFT", "REQUESTED", "APPROVED", "REJECTED", "SCHEDULED", "COMPLETED", "CANCELLED"}
)
