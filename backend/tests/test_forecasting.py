from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from app.data.tinkoff_history import build_tinkoff_feature_row, load_tinkoff_history
from app.evaluation.metrics import compute_metrics
from app.features.engineering import (
    build_daily_atm_dataset,
    chronological_split,
    create_time_series_features,
    get_atm_feature_frame,
    naive_baseline,
)
from app.ml.ensemble import predict_ensemble
from app.ml.inference import ProductionInferenceService
from app.ml.model_loader import (
    ModelArtifactCompatibilityError,
    ModelBundle,
    ModelConfigurationError,
    load_model_bundle,
)
from app.models.linear_regression_model import LinearRegressionModel
from app.models.random_forest_model import RandomForestModel
from app.services.forecast_service import ForecastService
from app.services.risk_service import CashRiskService


def test_feature_generation_includes_expected_columns() -> None:
    frame = get_atm_feature_frame("ATM-001")
    assert not frame.empty
    expected = {
        "lag_1",
        "lag_7",
        "lag_14",
        "rolling_7",
        "rolling_14",
        "rolling_30",
        "transaction_count",
        "avg_withdrawal_amount",
        "day_of_week",
        "weekend_flag",
        "month",
        "holiday_flag",
        "month_end_flag",
        "current_cash",
        "cash_buffer_ratio",
        "replenishment_gap",
    }
    assert expected.issubset(frame.columns)


def test_chronological_split_preserves_time_order() -> None:
    dataset = build_daily_atm_dataset(days=60)
    train_frame, validation_frame, test_frame = chronological_split(dataset, validation_fraction=0.2, test_fraction=0.2)
    assert len(train_frame) > 0
    assert len(validation_frame) > 0
    assert len(test_frame) > 0
    assert train_frame["date"].max() < validation_frame["date"].min()
    assert validation_frame["date"].max() < test_frame["date"].min()


def test_baseline_calculation_matches_previous_day_rule() -> None:
    series = pd.Series([10.0, 15.0, 18.0, 17.0])
    baseline = naive_baseline(series)
    assert baseline.iloc[0] == 10.0
    assert baseline.iloc[1] == 10.0
    assert baseline.iloc[2] == 15.0


def test_model_training_and_prediction_are_reproducible() -> None:
    frame = get_atm_feature_frame("ATM-001")
    feature_columns = [
        "lag_1",
        "lag_7",
        "lag_14",
        "rolling_7",
        "rolling_14",
        "rolling_30",
        "transaction_count",
        "avg_withdrawal_amount",
        "day_of_week",
        "weekend_flag",
        "month",
        "holiday_flag",
        "month_end_flag",
        "current_cash",
        "cash_buffer_ratio",
        "replenishment_gap",
    ]
    train_frame, validation_frame, _ = chronological_split(frame, validation_fraction=0.2, test_fraction=0.2)
    model = LinearRegressionModel()
    model.fit(train_frame[feature_columns].fillna(0), train_frame["target"])
    predictions = model.predict(validation_frame[feature_columns].fillna(0))
    assert len(predictions) == len(validation_frame)
    assert predictions.shape[0] > 0

    rf_model = RandomForestModel(random_state=42)
    rf_model.fit(train_frame[feature_columns].fillna(0), train_frame["target"])
    rf_predictions = rf_model.predict(validation_frame[feature_columns].fillna(0))
    assert len(rf_predictions) == len(validation_frame)


def test_evaluation_metrics_are_finite() -> None:
    actual = [100.0, 120.0, 130.0]
    predicted = [105.0, 122.0, 127.0]
    metrics = compute_metrics(actual, predicted)
    for name in ["mae", "rmse", "smape", "bias", "r2", "underforecast_rate"]:
        assert name in metrics
        assert isinstance(metrics[name], float)
    assert metrics["r2"] <= 1.0


def test_r_squared_matches_variance_explained_definition() -> None:
    actual = [1.0, 2.0, 3.0]
    predicted = [1.0, 2.0, 2.0]
    assert compute_metrics(actual, predicted)["r2"] == pytest.approx(0.5)


def test_forecast_generation_for_valid_atm(synthetic_processed_history) -> None:
    config = _production_config()
    models = {name: Mock() for name in ["linear_regression", "random_forest"]}
    models["linear_regression"].predict.return_value = [20000.0]
    models["random_forest"].predict.return_value = [30000.0]
    history = load_tinkoff_history(synthetic_processed_history)
    service = ForecastService(ProductionInferenceService(ModelBundle(models, config)), history_frame=history[history["atm_id"] == 74].reset_index(drop=True))
    result = service.generate_forecast("ATM-001", current_cash=32000.0, daily_demand=28000.0, capacity=50000.0)
    assert result.atm_id == "ATM-001"
    assert result.predicted_signed_net_cash_flow == 25000.0
    assert result.predicted_demand is None
    assert result.risk_level is None
    assert result.recommended_top_up is None
    assert result.risk_evaluation_status == "UNAVAILABLE"
    assert result.warning_threshold is None
    assert result.target == "next_day_cash_flow"
    assert result.forecast_date == "2018-10-01"
    assert result.source == "uploaded_dataset"


def test_invalid_atm_is_rejected() -> None:
    service = ForecastService()
    with pytest.raises(ValueError):
        service.generate_forecast("ATM-INVALID", current_cash=1000.0, daily_demand=2000.0, capacity=5000.0)


def test_forecast_requires_uploaded_history() -> None:
    service = ForecastService()
    with pytest.raises(ValueError, match="uploaded operational history is required"):
        service.generate_forecast("ATM-001", current_cash=1000.0, daily_demand=2000.0, capacity=5000.0)


def _production_config() -> dict[str, object]:
    config_path = Path(__file__).resolve().parents[2] / "backend" / "app" / "ml" / "artifacts" / "model_config.json"
    return json.loads(config_path.read_text(encoding="utf-8"))


def test_model_loader_loads_configured_model_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ml import model_loader

    config = _production_config()
    artifact_dir = Path("test-artifacts").resolve()
    config_path = artifact_dir / "model_config.json"
    original_is_file = Path.is_file
    original_read_text = Path.read_text

    def artifact_exists(path: Path) -> bool:
        if path == config_path or (path.parent == artifact_dir and path.name in {"linear_regression.joblib", "random_forest.joblib"}):
            return True
        return original_is_file(path)

    def read_config(path: Path, *args: object, **kwargs: object) -> str:
        if path == config_path:
            return json.dumps(config)
        return original_read_text(path, *args, **kwargs)

    loaded_paths: list[str] = []

    def load_artifact(path: Path) -> object:
        loaded_paths.append(path.name)
        return object()

    monkeypatch.setattr(model_loader, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(Path, "is_file", artifact_exists)
    monkeypatch.setattr(Path, "read_text", read_config)
    monkeypatch.setattr(model_loader.joblib, "load", load_artifact)
    load_model_bundle.cache_clear()

    try:
        bundle = load_model_bundle()
    finally:
        load_model_bundle.cache_clear()

    assert bundle.features == config["features"]
    assert set(bundle.models) == {"linear_regression", "random_forest"}
    assert loaded_paths == ["linear_regression.joblib", "random_forest.joblib"]


def test_model_loader_reports_missing_artifact(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ml import model_loader

    config = _production_config()
    monkeypatch.setattr(model_loader, "ARTIFACT_DIR", Path("missing-artifacts").resolve())
    monkeypatch.setattr(Path, "is_file", lambda path: path.name == "model_config.json")
    monkeypatch.setattr(Path, "read_text", lambda path, *args, **kwargs: json.dumps(config))
    load_model_bundle.cache_clear()
    try:
        with pytest.raises(ModelConfigurationError, match="Missing trained model artifact"):
            load_model_bundle()
    finally:
        load_model_bundle.cache_clear()


def test_supplied_artifacts_report_sklearn_compatibility() -> None:
    try:
        bundle = load_model_bundle()
    except ModelArtifactCompatibilityError as exc:
        assert "scikit-learn" in str(exc)
        assert "artifact was not modified" in str(exc)
    else:
        assert set(bundle.models) == {"linear_regression", "random_forest"}


def test_ensemble_uses_equal_model_weights() -> None:
    linear_model = Mock()
    linear_model.predict.return_value = [10.0]
    random_forest_model = Mock()
    random_forest_model.predict.return_value = [30.0]

    prediction = predict_ensemble(
        {"linear_regression": linear_model, "random_forest": random_forest_model},
        pd.DataFrame([[1.0]], columns=["feature"]),
    )

    assert prediction == 20.0


def test_inference_requires_configured_feature_order() -> None:
    models = {name: Mock() for name in ["linear_regression", "random_forest"]}
    bundle = ModelBundle(
        models=models,
        config={"features": ["first", "second"], "target": "next_day_cash_flow", "model_version": "v1"},
    )
    service = ProductionInferenceService(bundle)

    with pytest.raises(ValueError, match="feature names and order"):
        service.predict(pd.DataFrame([[1.0, 2.0]], columns=["second", "first"]))


def test_forecast_service_uses_configured_artifact_ensemble(synthetic_processed_history) -> None:
    config = _production_config()
    linear_model = Mock()
    linear_model.predict.return_value = [20000.0]
    random_forest_model = Mock()
    random_forest_model.predict.return_value = [30000.0]
    bundle = ModelBundle(
        models={"linear_regression": linear_model, "random_forest": random_forest_model},
        config=config,
    )
    history = load_tinkoff_history(synthetic_processed_history)
    service = ForecastService(ProductionInferenceService(bundle), history_frame=history[history["atm_id"] == 74].reset_index(drop=True))

    result = service.generate_forecast("ATM-001", current_cash=32000.0, daily_demand=28000.0, capacity=50000.0)

    assert result.predicted_signed_net_cash_flow == 25000.0
    assert result.predicted_demand is None
    assert result.risk_level is None
    assert result.risk_evaluation_status == "UNAVAILABLE"
    assert result.target == "next_day_cash_flow"
    assert result.forecast_date == "2018-10-01"
    assert result.model_name == "linear_regression+random_forest"
    assert linear_model.predict.call_args.args[0].columns.tolist() == config["features"]
    assert random_forest_model.predict.call_args.args[0].columns.tolist() == config["features"]


def test_tinkoff_history_loads_declared_schema(synthetic_processed_history) -> None:
    history = load_tinkoff_history(synthetic_processed_history)

    assert not history.empty
    assert set(history.columns) == {
        "atm_id",
        "datetime",
        "daily_cash_flow",
        "operation_count",
        "is_missing_observation",
    }
    assert history["atm_id"].nunique() == 20


def test_tinkoff_features_follow_configured_order(synthetic_processed_history) -> None:
    config = _production_config()

    features, forecast_date = build_tinkoff_feature_row("ATM-001", config["features"], synthetic_processed_history)

    assert features.columns.tolist() == config["features"]
    assert features.loc[0, "atm_id"] == 74
    assert features.loc[0, "lag_1"] == pytest.approx(590.0)
    assert forecast_date == "2018-10-01"


@pytest.mark.parametrize(
    ("projected_cash", "expected_risk"),
    [
        (1200.0, "NORMAL"),
        (900.0, "WARNING"),
        (400.0, "HIGH"),
        (100.0, "CRITICAL"),
    ],
)
def test_cash_risk_thresholds(projected_cash: float, expected_risk: str) -> None:
    risk = CashRiskService(
        warning_threshold=1.0,
        high_threshold=0.5,
        critical_threshold=0.25,
        safety_buffer=0.25,
    ).assess(current_cash=projected_cash + 1000.0, predicted_demand=1000.0, capacity=5000.0)

    assert risk.projected_cash == projected_cash
    assert risk.risk_level == expected_risk


def test_replenishment_targets_demand_plus_buffer() -> None:
    risk = CashRiskService(safety_buffer=0.25).assess(
        current_cash=800.0,
        predicted_demand=1000.0,
        capacity=5000.0,
    )

    assert risk.projected_cash == 0.0
    assert risk.recommended_top_up == 1250.0


def test_replenishment_respects_capacity_and_never_goes_negative() -> None:
    service = CashRiskService(safety_buffer=0.25)
    at_capacity = service.assess(current_cash=900.0, predicted_demand=1000.0, capacity=1000.0)

    assert 0 <= at_capacity.recommended_top_up <= 1000.0


def test_negative_signed_flow_is_rejected_by_demand_risk_service() -> None:
    with pytest.raises(ValueError, match="nonnegative verified withdrawal-demand"):
        CashRiskService().assess(current_cash=32000.0, predicted_demand=-3199.96, capacity=50000.0)


def test_invalid_prototype_mapping_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.data import tinkoff_history

    monkeypatch.setenv("PROTOTYPE_ATM_ID_MAP", "not-json")

    with pytest.raises(ValueError, match="PROTOTYPE_ATM_ID_MAP"):
        tinkoff_history.get_prototype_atm_mapping()
