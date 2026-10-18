"""Time-safe evaluation of the production ATM cash-flow forecast.

This script evaluates one-step-ahead forecasts only. It uses date-level
chronological splits, expanding baselines, and rolling-origin folds so every
prediction is made using information available before its forecast date.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.data.tinkoff_history import REQUIRED_HISTORY_COLUMNS, build_calendar_aligned_tinkoff_feature_frame
from app.ml.model_loader import load_model_bundle
from app.models.experiment_models import get_model


FEATURES = [
    "atm_id",
    "operation_count",
    "is_missing_observation",
    "day_of_week",
    "is_weekend",
    "day_of_month",
    "month",
    "week_of_year",
    "is_month_end",
    "lag_1",
    "lag_7",
    "lag_14",
    "rolling_7",
    "rolling_14",
    "rolling_30",
    "operation_count_lag_1",
    "operation_count_rolling_7",
]


def load_history(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw = pd.read_csv(path)
    missing = REQUIRED_HISTORY_COLUMNS.difference(raw.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    frame = raw[list(REQUIRED_HISTORY_COLUMNS)].copy()
    frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce")
    for column in ("atm_id", "daily_cash_flow", "operation_count", "is_missing_observation"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame[list(REQUIRED_HISTORY_COLUMNS)].isna().any().any():
        raise ValueError("History contains null or malformed required values")
    duplicate_count = int(frame.duplicated(["atm_id", "datetime"]).sum())
    if duplicate_count:
        raise ValueError(f"History contains {duplicate_count} duplicate ATM/date rows")
    frame["atm_id"] = frame["atm_id"].astype(int)
    frame = frame.sort_values(["atm_id", "datetime"]).reset_index(drop=True)
    summary = {
        "rows": int(len(frame)),
        "atms": int(frame["atm_id"].nunique()),
        "date_from": frame["datetime"].min().date().isoformat(),
        "date_to": frame["datetime"].max().date().isoformat(),
        "unique_dates": int(frame["datetime"].dt.normalize().nunique()),
        "duplicate_atm_datetime": duplicate_count,
        "missing_observation_rows": int(frame["is_missing_observation"].sum()),
        "zero_flow_rows": int((frame["daily_cash_flow"] == 0).sum()),
        "negative_flow_rows": int((frame["daily_cash_flow"] < 0).sum()),
        "flow_min": float(frame["daily_cash_flow"].min()),
        "flow_max": float(frame["daily_cash_flow"].max()),
    }
    return frame, summary


def build_feature_frame(history: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    frame, alignment = build_calendar_aligned_tinkoff_feature_frame(history)
    date_lookup = history.set_index(["atm_id", "datetime"])["daily_cash_flow"]
    previous_week: list[float] = []
    for row in frame.itertuples(index=False):
        key = (row.atm_id, row.forecast_date - pd.Timedelta(days=7))
        previous_week.append(float(date_lookup.get(key, np.nan)))
    frame["previous_week_same_weekday"] = previous_week
    return frame, alignment


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | None]:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    error = predicted - actual
    denominator = float(np.abs(actual).sum())
    return {
        "sample_count": int(actual.size),
        "mae": float(np.abs(error).mean()),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "wape_pct": float(np.abs(error).sum() / denominator * 100) if denominator else None,
        "bias_mean": float(error.mean()),
        "bias_pct_of_abs_actual": float(error.sum() / denominator * 100) if denominator else None,
        "underforecast_rate_pct": float((predicted < actual).mean() * 100),
    }


def predict_baselines(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    return {
        "historical_mean": frame["historical_mean"].to_numpy(dtype=float),
        "previous_week_same_weekday": frame["previous_week_same_weekday"].to_numpy(dtype=float),
    }


def fit_ensemble(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    predictions: list[np.ndarray] = []
    x_train = train[FEATURES].fillna(0)
    x_test = test[FEATURES].fillna(0)
    for name in ("linear_regression", "random_forest"):
        model = get_model(name, random_state=42)
        model.fit(x_train, train["target"])
        predictions.append(np.asarray(model.predict(x_test), dtype=float))
    return np.mean(predictions, axis=0)


def evaluate_split(frame: pd.DataFrame, train_end: pd.Timestamp, test_dates: pd.DatetimeIndex, persisted: Any) -> dict[str, Any]:
    train = frame[frame["forecast_date"] <= train_end].copy()
    test = frame[frame["forecast_date"].isin(test_dates)].copy()
    actual = test["target"].to_numpy(dtype=float)
    rows: dict[str, dict[str, float | None]] = {}
    baselines = predict_baselines(test)
    for name, values in baselines.items():
        valid = np.isfinite(values)
        rows[name] = metrics(actual[valid], values[valid])

    bundle_predictions = np.asarray(persisted.predict(test[FEATURES].fillna(0)), dtype=float)
    rows["persisted_ensemble"] = metrics(actual, bundle_predictions)
    rows["retrained_ensemble"] = metrics(actual, fit_ensemble(train, test))
    return {
        "train_end": train_end.date().isoformat(),
        "test_from": test_dates.min().date().isoformat(),
        "test_to": test_dates.max().date().isoformat(),
        "models": rows,
        "samples_with_previous_week_baseline": int(np.isfinite(baselines["previous_week_same_weekday"]).sum()),
        "sample_count": int(len(test)),
    }


def by_atm(frame: pd.DataFrame, test_dates: pd.DatetimeIndex, persisted: Any) -> list[dict[str, Any]]:
    test = frame[frame["forecast_date"].isin(test_dates)].copy()
    output: list[dict[str, Any]] = []
    for atm_id, group in test.groupby("atm_id"):
        actual = group["target"].to_numpy(dtype=float)
        predictions = np.asarray(persisted.predict(group[FEATURES].fillna(0)), dtype=float)
        baseline = group["previous_week_same_weekday"].to_numpy(dtype=float)
        valid = np.isfinite(baseline)
        output.append(
            {
                "atm_id": int(atm_id),
                "persisted_ensemble": metrics(actual, predictions),
                "previous_week_same_weekday": metrics(actual[valid], baseline[valid]),
            }
        )
    return output


def rolling_origin(frame: pd.DataFrame, persisted: Any, folds: int = 5, window_days: int = 14) -> list[dict[str, Any]]:
    dates = pd.DatetimeIndex(sorted(frame["forecast_date"].unique()))
    first_test_index = max(30, len(dates) - folds * window_days)
    results: list[dict[str, Any]] = []
    for fold in range(folds):
        start = first_test_index + fold * window_days
        test_dates = dates[start : start + window_days]
        if len(test_dates) == 0:
            continue
        results.append(evaluate_split(frame, dates[start - 1], test_dates, persisted))
    return results


def run(path: Path) -> dict[str, Any]:
    history, summary = load_history(path)
    frame, alignment = build_feature_frame(history)
    bundle = load_model_bundle()
    if bundle.features != FEATURES:
        raise ValueError(f"Artifact feature list differs from evaluator: {bundle.features}")
    dates = pd.DatetimeIndex(sorted(frame["forecast_date"].unique()))
    train_end_index = int(len(dates) * 0.6) - 1
    validation_end_index = int(len(dates) * 0.8) - 1
    test_dates = dates[validation_end_index + 1 :]
    # The persisted bundle is evaluated separately because its models are not a
    # single estimator; use the ensemble wrapper for both persisted predictions.
    class PersistedEnsemble:
        def predict(self, values: pd.DataFrame) -> np.ndarray:
            linear = np.asarray(bundle.models["linear_regression"].predict(values), dtype=float)
            forest = np.asarray(bundle.models["random_forest"].predict(values), dtype=float)
            return 0.5 * linear + 0.5 * forest

    persisted = PersistedEnsemble()
    holdout = evaluate_split(frame, dates[train_end_index], test_dates, persisted)
    holdout["validation_end"] = dates[validation_end_index].date().isoformat()
    return {
        "data": summary,
        "target": "next-day daily_cash_flow (signed; source field, not verified withdrawal demand)",
        "horizon_days": [1],
        "split_method": "unique-date chronological 60% train / 20% validation / 20% test; no test-set model selection",
        "feature_frame_rows": int(len(frame)),
        "target_alignment": alignment,
        "holdout": holdout,
        "by_atm_holdout": by_atm(frame, test_dates, persisted),
        "rolling_origin": rolling_origin(frame, persisted),
        "zero_demand_handling": "MAE/RMSE/bias retain zero targets; WAPE denominator is sum(abs(actual)), so zero-only windows would be reported as undefined; same-weekday rows without history are excluded only from that baseline.",
        "artifact_model_version": bundle.model_version,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--history",
        type=Path,
        required=True,
        help="Path to an explicitly selected local history CSV; private source data is not included.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run(args.history)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
