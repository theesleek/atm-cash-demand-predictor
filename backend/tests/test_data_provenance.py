from __future__ import annotations

import pandas as pd
import pytest

from app.data.tinkoff_history import (
    build_calendar_aligned_tinkoff_feature_frame,
    load_tinkoff_history,
    reconstruct_tinkoff_signed_daily_flow,
)


def test_processed_history_preserves_signed_values_and_distinguishes_missing_rows(synthetic_processed_history) -> None:
    history = load_tinkoff_history(synthetic_processed_history)

    assert set(history.columns) == {
        "atm_id",
        "datetime",
        "daily_cash_flow",
        "operation_count",
        "is_missing_observation",
    }
    assert len(history) == 600
    assert history.duplicated(["atm_id", "datetime"]).sum() == 0
    assert (history["daily_cash_flow"] < 0).any()
    assert (history["daily_cash_flow"] == 0).any()

    missing = history[history["is_missing_observation"] == 1]
    assert len(missing) == 2
    assert (missing["daily_cash_flow"] == 0).all()
    assert (missing["operation_count"] == 0).all()

    observed_zero = history[
        (history["is_missing_observation"] == 0) & (history["daily_cash_flow"] == 0)
    ]
    assert not observed_zero.empty
    assert (observed_zero["operation_count"] > 0).all()


def test_duplicate_atm_datetime_policy_keeps_last_record(tmp_path) -> None:
    path = tmp_path / "history.csv"
    pd.DataFrame(
        [
            {"atm_id": 74, "datetime": "2018-01-01", "daily_cash_flow": -10, "operation_count": 1, "is_missing_observation": 0},
            {"atm_id": 74, "datetime": "2018-01-01", "daily_cash_flow": -20, "operation_count": 2, "is_missing_observation": 0},
        ]
    ).to_csv(path, index=False)

    history = load_tinkoff_history(path)

    assert len(history) == 1
    assert history.iloc[0]["daily_cash_flow"] == -20
    assert history.iloc[0]["operation_count"] == 2


def test_raw_operation_aggregation_sums_each_atm_day_and_keeps_duplicate_rows(tmp_path) -> None:
    path = tmp_path / "train_kaggle.csv"
    pd.DataFrame(
        [
            {"datetime": "2018-01-01", "atm_id": 74, "operation_value": 10.5},
            {"datetime": "2018-01-01", "atm_id": 74, "operation_value": -2.5},
            {"datetime": "2018-01-01", "atm_id": 74, "operation_value": -2.5},
            {"datetime": "2018-01-02", "atm_id": 74, "operation_value": 3},
            {"datetime": "not-a-date", "atm_id": 74, "operation_value": 99},
        ]
    ).to_csv(path, index=False)

    daily = reconstruct_tinkoff_signed_daily_flow(path)

    assert daily.to_dict("records") == [
        {
            "atm_id": 74,
            "datetime": pd.Timestamp("2018-01-01"),
            "daily_cash_flow": 5.5,
            "operation_count": 3,
        },
        {
            "atm_id": 74,
            "datetime": pd.Timestamp("2018-01-02"),
            "daily_cash_flow": 3.0,
            "operation_count": 1,
        },
    ]


def test_raw_operation_aggregation_requires_reconstruction_fields(tmp_path) -> None:
    path = tmp_path / "incomplete.csv"
    pd.DataFrame([{"datetime": "2018-01-01", "atm_id": 74}]).to_csv(path, index=False)

    with pytest.raises(ValueError, match="operation_value"):
        reconstruct_tinkoff_signed_daily_flow(path)


def test_calendar_target_alignment_requires_an_observed_next_calendar_day() -> None:
    history = pd.DataFrame(
        [
            {"atm_id": 74, "datetime": "2018-01-01", "daily_cash_flow": 10, "operation_count": 1, "is_missing_observation": 0},
            {"atm_id": 74, "datetime": "2018-01-02", "daily_cash_flow": 20, "operation_count": 2, "is_missing_observation": 0},
            {"atm_id": 74, "datetime": "2018-01-04", "daily_cash_flow": 40, "operation_count": 4, "is_missing_observation": 0},
            {"atm_id": 85, "datetime": "2018-01-01", "daily_cash_flow": 100, "operation_count": 10, "is_missing_observation": 0},
            {"atm_id": 85, "datetime": "2018-01-02", "daily_cash_flow": 200, "operation_count": 20, "is_missing_observation": 1},
            {"atm_id": 85, "datetime": "2018-01-03", "daily_cash_flow": 300, "operation_count": 30, "is_missing_observation": 0},
        ]
    )

    frame, alignment = build_calendar_aligned_tinkoff_feature_frame(history)

    assert frame[["atm_id", "datetime", "forecast_date", "target"]].to_dict("records") == [
        {
            "atm_id": 74,
            "datetime": pd.Timestamp("2018-01-01"),
            "forecast_date": pd.Timestamp("2018-01-02"),
            "target": 20.0,
        }
    ]
    assert alignment == {
        "source_rows": 6,
        "source_missing_placeholders": 1,
        "eligible_source_rows": 5,
        "excluded_next_date_absent": 3,
        "excluded_next_date_missing_placeholder": 1,
        "valid_target_rows": 1,
    }


def test_calendar_target_alignment_keeps_atms_separate_and_does_not_borrow_gap_values() -> None:
    history = pd.DataFrame(
        [
            {"atm_id": 74, "datetime": "2018-01-01", "daily_cash_flow": 10, "operation_count": 1, "is_missing_observation": 0},
            {"atm_id": 74, "datetime": "2018-01-02", "daily_cash_flow": 20, "operation_count": 2, "is_missing_observation": 0},
            {"atm_id": 74, "datetime": "2018-01-03", "daily_cash_flow": 30, "operation_count": 3, "is_missing_observation": 0},
            {"atm_id": 85, "datetime": "2018-01-01", "daily_cash_flow": 100, "operation_count": 10, "is_missing_observation": 0},
            {"atm_id": 85, "datetime": "2018-01-03", "daily_cash_flow": 300, "operation_count": 30, "is_missing_observation": 0},
        ]
    )

    frame, _ = build_calendar_aligned_tinkoff_feature_frame(history)

    assert frame[["atm_id", "datetime", "target"]].to_dict("records") == [
        {"atm_id": 74, "datetime": pd.Timestamp("2018-01-01"), "target": 20.0},
        {"atm_id": 74, "datetime": pd.Timestamp("2018-01-02"), "target": 30.0},
    ]
    assert frame.loc[frame["datetime"] == pd.Timestamp("2018-01-02"), "lag_1"].iloc[0] == 10.0
