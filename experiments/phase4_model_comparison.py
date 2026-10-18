from __future__ import annotations

import pandas as pd

from app.evaluation.metrics import compute_metrics
from app.features.engineering import build_daily_atm_dataset, chronological_split, create_time_series_features
from app.models.experiment_models import get_model


def run_comparison() -> list[dict[str, object]]:
    dataset = build_daily_atm_dataset(days=180)
    feature_frame = create_time_series_features(dataset)
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
    train_frame, validation_frame, _ = chronological_split(feature_frame, validation_fraction=0.2, test_fraction=0.2)

    results: list[dict[str, object]] = []
    for model_name in ["linear_regression", "random_forest"]:
        model = get_model(model_name, random_state=42)
        model.fit(train_frame[feature_columns].fillna(0), train_frame["target"])
        predictions = model.predict(validation_frame[feature_columns].fillna(0))
        metrics = compute_metrics(validation_frame["target"].to_numpy(), predictions)
        results.append({"model": model_name, **metrics})

    return results


if __name__ == "__main__":
    comparison = run_comparison()
    for row in comparison:
        print(row)
