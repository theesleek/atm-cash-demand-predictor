from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy.orm import Session

from app.ml.model_loader import ARTIFACT_DIR, load_model_bundle
from app.services.model_evaluation_service import get_model_evaluation


def get_model_metadata(*, session: Session | None = None, history_path: Path | None = None) -> dict[str, object]:
    bundle = load_model_bundle()
    evaluation = get_model_evaluation(session=session, history_path=history_path)
    selected = next((model for model in evaluation["models"] if model["model"] == evaluation["selected_model"]), None)
    artifacts = []
    for model_name in ("linear_regression", "random_forest"):
        path = Path(ARTIFACT_DIR) / f"{model_name}.joblib"
        artifacts.append({
            "model_name": model_name,
            "artifact_id": path.name,
            "checksum": f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}",
        })
    return {
        "model_name": "linear_regression+random_forest",
        "model_version": bundle.model_version,
        "training_timestamp": bundle.config.get("training_timestamp"),
        "dataset_version": bundle.config.get("dataset_version", "not-recorded"),
        "feature_version": bundle.config.get("feature_version", "production-features-v1"),
        "status": bundle.config.get("status", "ACTIVE"),
        "artifacts": artifacts,
        "evaluation": selected,
        "evaluation_status": evaluation.get("status"),
        "evaluation_reason": evaluation.get("reason"),
        "evaluation_sample_count": selected.get("sample_count") if selected else None,
    }
