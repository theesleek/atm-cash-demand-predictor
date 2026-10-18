from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Mapping

from sqlalchemy.orm import Session

from app.models.atm import utcnow
from app.models.model_registry import ModelRegistry
from app.services.audit_service import AuditService
from app.ml.model_loader import ARTIFACT_DIR, load_model_bundle
from app.services.model_evaluation_service import get_model_evaluation


REQUIRED_METRICS = ("mae", "rmse", "bias", "r2")


class ModelLifecycleError(ValueError):
    pass


class ModelLifecycleService:
    def __init__(self, session: Session):
        self.session = session

    def register_trained(
        self,
        *,
        target: str,
        model_name: str,
        model_version: str,
        dataset_version: str,
        feature_version: str,
        artifacts: Mapping[str, str | Path],
        actor_id: int | None,
        source: str = "API",
    ) -> ModelRegistry:
        if self.session.query(ModelRegistry).filter_by(target=target, model_version=model_version).first():
            raise ModelLifecycleError("Model version is already registered")
        checksums = self._artifact_checksums(artifacts)
        record = ModelRegistry(
            target=target,
            model_name=model_name,
            model_version=model_version,
            dataset_version=dataset_version,
            feature_version=feature_version,
            status="TRAINED",
            artifact_checksums=checksums,
        )
        self.session.add(record)
        self.session.flush()
        self._audit(actor_id, "MODEL_TRAINED", record, source, {"model_version": model_version})
        self.session.commit()
        self.session.refresh(record)
        return record

    def evaluate(self, model_version: str, metrics: Mapping[str, object], actor_id: int | None, source: str = "API") -> ModelRegistry:
        record = self._record(model_version)
        self._require_status(record, "TRAINED")
        self._validate_metrics(metrics)
        record.metrics = dict(metrics)
        record.status = "EVALUATED"
        record.evaluated_at = utcnow()
        self._audit(actor_id, "MODEL_EVALUATED", record, source, {"model_version": record.model_version, "metrics": dict(metrics)})
        self.session.commit()
        return record

    def approve(self, model_version: str, actor_id: int | None, source: str = "API") -> ModelRegistry:
        record = self._record(model_version)
        self._require_status(record, "EVALUATED")
        self._validate_metrics(record.metrics)
        record.status = "APPROVED"
        record.approved_at = utcnow()
        self._audit(actor_id, "MODEL_APPROVED", record, source, {"model_version": record.model_version})
        self.session.commit()
        return record

    def activate(self, model_version: str, actor_id: int | None, artifacts: Mapping[str, str | Path], source: str = "API", rollback: bool = False) -> ModelRegistry:
        record = self._record(model_version)
        allowed = {"APPROVED", "RETIRED"} if rollback else {"APPROVED"}
        if record.status not in allowed or record.approved_at is None:
            raise ModelLifecycleError("Only an approved model can become active")
        if self._artifact_checksums(artifacts) != record.artifact_checksums:
            raise ModelLifecycleError("Model artifacts failed integrity validation")
        active = self.session.query(ModelRegistry).filter_by(target=record.target, status="ACTIVE").with_for_update().first()
        if active is not None and active.id != record.id:
            active.status = "RETIRED"
            active.retired_at = utcnow()
            self._audit(actor_id, "MODEL_RETIRED", active, source, {"model_version": active.model_version, "replacement": record.model_version})
        record.status = "ACTIVE"
        record.activated_at = utcnow()
        self._audit(actor_id, "MODEL_ROLLBACK" if rollback else "MODEL_ACTIVATED", record, source, {"model_version": record.model_version})
        self.session.commit()
        return record

    def retire(self, model_version: str, actor_id: int | None, source: str = "API") -> ModelRegistry:
        record = self._record(model_version)
        self._require_status(record, "ACTIVE")
        record.status = "RETIRED"
        record.retired_at = utcnow()
        self._audit(actor_id, "MODEL_RETIRED", record, source, {"model_version": record.model_version})
        self.session.commit()
        return record

    def _record(self, model_version: str) -> ModelRegistry:
        record = self.session.query(ModelRegistry).filter_by(model_version=model_version).one_or_none()
        if record is None:
            raise ModelLifecycleError("Unknown model version")
        return record

    @staticmethod
    def _require_status(record: ModelRegistry, expected: str) -> None:
        if record.status != expected:
            raise ModelLifecycleError(f"Model must be {expected} before this transition")

    @staticmethod
    def _validate_metrics(metrics: Mapping[str, object]) -> None:
        if any(key not in metrics or not isinstance(metrics[key], (int, float)) or not math.isfinite(float(metrics[key])) for key in REQUIRED_METRICS):
            raise ModelLifecycleError("Evaluation must contain finite MAE, RMSE, Bias, and R² metrics")

    @staticmethod
    def _artifact_checksums(artifacts: Mapping[str, str | Path]) -> dict[str, str]:
        if not artifacts:
            raise ModelLifecycleError("At least one model artifact is required")
        checksums: dict[str, str] = {}
        for name, raw_path in artifacts.items():
            path = Path(raw_path)
            if not path.is_file():
                raise ModelLifecycleError(f"Missing model artifact: {name}")
            checksums[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return checksums

    def _audit(self, actor_id: int | None, action: str, record: ModelRegistry, source: str, metadata: dict[str, object]) -> None:
        AuditService(self.session).record(actor_id, action, "MODEL", record.model_version, source, metadata, commit=False)


def ensure_production_model_registered(session: Session) -> None:
    """Register the checked-in production bundle once, without replacing a governed model."""
    bundle = load_model_bundle()
    target = str(bundle.config["target"])
    version = bundle.model_version or "unknown"
    if session.query(ModelRegistry).filter_by(target=target, model_version=version).first() is not None:
        return
    evaluation = get_model_evaluation(session=session)
    if evaluation.get("status") != "AVAILABLE":
        return
    selected = next(row for row in evaluation["models"] if row["model"] == evaluation["selected_model"])
    artifacts = {name: ARTIFACT_DIR / f"{name}.joblib" for name in bundle.models}
    lifecycle = ModelLifecycleService(session)
    lifecycle.register_trained(
        target=target,
        model_name="linear_regression+random_forest",
        model_version=version,
        dataset_version=str(bundle.config.get("dataset_version", "not-recorded")),
        feature_version=str(bundle.config.get("feature_version", "production-features-v1")),
        artifacts=artifacts,
        actor_id=None,
        source="SYSTEM",
    )
    lifecycle.evaluate(version, {key: selected[key] for key in REQUIRED_METRICS}, actor_id=None, source="SYSTEM")
    lifecycle.approve(version, actor_id=None, source="SYSTEM")
    lifecycle.activate(version, actor_id=None, artifacts=artifacts, source="SYSTEM")
