from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.data.tinkoff_history import build_calendar_aligned_tinkoff_feature_frame, load_tinkoff_history
from app.evaluation.metrics import compute_metrics
from app.features.engineering import chronological_split
from app.ml.ensemble import predict_ensemble
from app.ml.model_loader import ModelConfigurationError, load_model_bundle
from app.services.uploaded_history_service import load_uploaded_history


def _unavailable_evaluation(reason: str, source: str) -> dict[str, object]:
    return {
        "status": "UNAVAILABLE",
        "reason": reason,
        "data_source": source,
        "models": [],
        "selected_model": None,
        "features": [],
    }


def _production_feature_frame(history: pd.DataFrame) -> pd.DataFrame:
    frame, _ = build_calendar_aligned_tinkoff_feature_frame(history)
    return frame


def _feature_importance(model: Any, features: list[str]) -> list[dict[str, object]]:
    values = getattr(model, "feature_importances_", None)
    if values is None:
        coefficients = getattr(model, "coef_", None)
        values = np.abs(np.asarray(coefficients, dtype=float).reshape(-1)) if coefficients is not None else None
    if values is None:
        return []
    pairs = sorted(zip(features, np.asarray(values, dtype=float)), key=lambda item: item[1], reverse=True)
    total = sum(value for _, value in pairs)
    return [
        {"feature": feature, "importance": round(float(value / total), 6) if total else 0.0}
        for feature, value in pairs[:10]
    ]


def _metric_row(
    name: str,
    predictions: np.ndarray,
    actual: np.ndarray,
    split: str,
    sample_count: int,
    model_version: str | None,
    feature_importance: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    metrics = compute_metrics(actual, predictions)
    return {
        "model": name,
        "status": "available",
        "mae": round(metrics["mae"], 6),
        "rmse": round(metrics["rmse"], 6),
        "bias": round(metrics["bias"], 6),
        "r2": round(metrics["r2"], 6),
        "evaluation_split": split,
        "sample_count": sample_count,
        "model_version": model_version,
        "feature_importance": feature_importance or [],
    }


def _unavailable_row(name: str, split: str, sample_count: int, reason: str) -> dict[str, object]:
    return {
        "model": name,
        "status": "unavailable",
        "mae": None,
        "rmse": None,
        "bias": None,
        "r2": None,
        "evaluation_split": split,
        "sample_count": sample_count,
        "model_version": None,
        "feature_importance": [],
        "reason": reason,
    }


def get_model_evaluation(
    *,
    session: Session | None = None,
    history_path: Path | None = None,
) -> dict[str, object]:
    if history_path is not None:
        history = load_tinkoff_history(history_path)
        source = "explicit_local_file"
    elif session is not None:
        history = load_uploaded_history(session)
        source = "uploaded_database"
    else:
        return _unavailable_evaluation("No uploaded operational history is available.", "uploaded_database")
    if history is None or history.empty:
        return _unavailable_evaluation("The selected history source contains no records.", source)

    bundle = load_model_bundle()
    frame = _production_feature_frame(history)
    if frame.empty:
        return _unavailable_evaluation("The selected history contains no valid next-day targets.", source)

    train, _, test = chronological_split(frame, validation_fraction=0.2, test_fraction=0.2)
    features = bundle.features
    X_test = test[features].fillna(0)
    actual = test["target"].to_numpy(dtype=float)
    split = "chronological 60/20/20 test split"
    sample_count = len(test)
    available_models: list[dict[str, object]] = []

    baseline = test["rolling_7"].fillna(0).to_numpy(dtype=float)
    available_models.append(_metric_row("7_day_average", baseline, actual, split, sample_count, "baseline-7-day-average"))

    predictions: dict[str, np.ndarray] = {}
    importance_by_model: dict[str, list[dict[str, object]]] = {}
    for model_name in ("linear_regression", "random_forest"):
        model = bundle.models[model_name]
        values = np.asarray(model.predict(X_test), dtype=float)
        predictions[model_name] = values
        importance_by_model[model_name] = _feature_importance(model, features)
        available_models.append(
            _metric_row(model_name, values, actual, split, sample_count, bundle.model_version, importance_by_model[model_name])
        )

    ensemble_predictions = np.asarray(
        0.5 * predictions["linear_regression"] + 0.5 * predictions["random_forest"],
        dtype=float,
    )
    linear_importance = {item["feature"]: float(item["importance"]) for item in importance_by_model["linear_regression"]}
    forest_importance = {item["feature"]: float(item["importance"]) for item in importance_by_model["random_forest"]}
    ensemble_importance = [
        {"feature": feature, "importance": round((linear_importance.get(feature, 0.0) + forest_importance.get(feature, 0.0)) / 2, 6)}
        for feature in features
    ]
    ensemble_importance.sort(key=lambda item: item["importance"], reverse=True)
    available_models.append(_metric_row("ensemble", ensemble_predictions, actual, split, sample_count, bundle.model_version, ensemble_importance[:10]))

    for model_name, package_name in (("xgboost", "xgboost"), ("lightgbm", "lightgbm")):
        if find_spec(package_name) is None:
            available_models.insert(
                3 if model_name == "xgboost" else 4,
                _unavailable_row(model_name, split, sample_count, f"Optional dependency '{package_name}' is not installed."),
            )
            continue
        if package_name == "xgboost":
            from xgboost import XGBRegressor

            model = XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.05, random_state=42, n_jobs=1)
        else:
            from lightgbm import LGBMRegressor

            model = LGBMRegressor(n_estimators=200, learning_rate=0.05, random_state=42, verbosity=-1)
        model.fit(train[features].fillna(0), train["target"])
        values = np.asarray(model.predict(X_test), dtype=float)
        available_models.insert(
            3 if model_name == "xgboost" else 4,
            _metric_row(model_name, values, actual, split, sample_count, "phase22-evaluation", _feature_importance(model, features)),
        )

    return {
        "status": "AVAILABLE",
        "reason": None,
        "target": bundle.config["target"],
        "data_source": source,
        "model_version": bundle.model_version,
        "model_metadata": {
            "model_name": "linear_regression+random_forest",
            "model_version": bundle.model_version,
            "dataset_version": bundle.config.get("dataset_version", "not-recorded"),
            "feature_version": bundle.config.get("feature_version", "production-features-v1"),
            "status": bundle.config.get("status", "ACTIVE"),
        },
        "features": features,
        "models": available_models,
        "selected_model": "ensemble",
        "interpretation": {
            "mae": "Lower MAE means smaller average absolute error.",
            "rmse": "Lower RMSE means fewer or lower large errors.",
            "bias": "Bias closer to 0 means less systematic over- or underprediction.",
            "r2": "Higher R² means more variance explained.",
        },
    }
