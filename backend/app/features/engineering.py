from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from app.data.atm_data import get_atm_records


DEFAULT_FEATURE_COLUMNS = [
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


def build_daily_atm_dataset(days: int = 180, random_seed: int = 42) -> pd.DataFrame:
    records = get_atm_records()
    if not records:
        return pd.DataFrame(columns=["atm_code", "date", "demand_target", "capacity", "current_cash", "transaction_count", "avg_withdrawal_amount"])

    rng = np.random.default_rng(random_seed)
    start_date = pd.Timestamp("2025-01-01")
    rows: list[dict[str, object]] = []

    for index, record in enumerate(records):
        atm_code = str(record["atm_code"])
        base_demand = float(record["daily_demand"])
        capacity = float(record["capacity"])
        initial_cash = float(record["current_cash"])
        trend_offset = 0.15 + (index * 0.08)
        seasonal_seed = index + 1

        for day_offset in range(days):
            date = start_date + pd.Timedelta(days=day_offset)
            seasonal_wave = 1 + 0.18 * np.sin((day_offset + seasonal_seed) / 6.5)
            weekly_pattern = 1.18 if date.dayofweek >= 5 else 1.0
            month_end_factor = 1.12 if date.is_month_end else 1.0
            noise = 1 + rng.normal(0, 0.09)
            demand = max(base_demand * seasonal_wave * weekly_pattern * month_end_factor * noise * (1 + trend_offset), 150.0)
            transaction_count = max(12, int(round(demand / (80 + (index * 8)))))
            avg_withdrawal_amount = demand / max(transaction_count, 1)
            cash_buffer = max(0.0, initial_cash + (day_offset * 120) - (demand * 0.7))
            current_cash = min(capacity, max(0.0, cash_buffer + rng.normal(0, 500)))
            replenishment_gap = max(0.0, demand * 1.1 + capacity * 0.1 - current_cash)

            rows.append(
                {
                    "atm_code": atm_code,
                    "date": date,
                    "demand_target": round(float(demand), 2),
                    "capacity": round(capacity, 2),
                    "current_cash": round(current_cash, 2),
                    "transaction_count": int(transaction_count),
                    "avg_withdrawal_amount": round(float(avg_withdrawal_amount), 2),
                    "day_of_week": int(date.dayofweek),
                    "weekend_flag": int(date.dayofweek >= 5),
                    "month": int(date.month),
                    "holiday_flag": 0,
                    "month_end_flag": int(date.is_month_end),
                    "cash_buffer_ratio": round(float(current_cash / max(capacity, 1.0)), 4),
                    "replenishment_gap": round(float(replenishment_gap), 2),
                    "upi_share": 0.0,
                }
            )

    frame = pd.DataFrame(rows)
    return validate_and_clean_dataset(frame)


def validate_and_clean_dataset(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame

    cleaned = frame.copy()
    cleaned["date"] = pd.to_datetime(cleaned["date"], errors="coerce")
    cleaned = cleaned.dropna(subset=["atm_code", "date"]).copy()
    cleaned = cleaned.sort_values(["atm_code", "date"]).drop_duplicates(subset=["atm_code", "date"], keep="last")

    numeric_columns = [
        "demand_target",
        "capacity",
        "current_cash",
        "transaction_count",
        "avg_withdrawal_amount",
        "cash_buffer_ratio",
        "replenishment_gap",
    ]
    for column in numeric_columns:
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")

    cleaned["demand_target"] = cleaned.groupby("atm_code")["demand_target"].transform(
        lambda values: values.fillna(values.median())
    )
    cleaned["current_cash"] = cleaned.groupby("atm_code")["current_cash"].transform(
        lambda values: values.fillna(values.median())
    )
    cleaned["transaction_count"] = cleaned["transaction_count"].fillna(0).astype(int)
    cleaned["avg_withdrawal_amount"] = cleaned["avg_withdrawal_amount"].fillna(cleaned["demand_target"] / cleaned["transaction_count"].replace(0, 1))
    cleaned["capacity"] = cleaned["capacity"].fillna(cleaned["demand_target"].median())
    cleaned["day_of_week"] = cleaned["date"].dt.dayofweek
    cleaned["weekend_flag"] = (cleaned["day_of_week"] >= 5).astype(int)
    cleaned["month"] = cleaned["date"].dt.month
    cleaned["holiday_flag"] = 0
    cleaned["month_end_flag"] = cleaned["date"].dt.is_month_end.astype(int)
    cleaned["cash_buffer_ratio"] = cleaned["current_cash"] / cleaned["capacity"].replace(0, np.nan)
    cleaned["replenishment_gap"] = np.maximum(0.0, cleaned["demand_target"] * 1.1 + cleaned["capacity"] * 0.1 - cleaned["current_cash"])
    cleaned["upi_share"] = cleaned.get("upi_share", 0.0)
    return cleaned.reset_index(drop=True)


def create_time_series_features(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame

    ordered = frame.sort_values(["atm_code", "date"]).copy()
    ordered["lag_1"] = ordered.groupby("atm_code")["demand_target"].shift(1)
    ordered["lag_7"] = ordered.groupby("atm_code")["demand_target"].shift(7)
    ordered["lag_14"] = ordered.groupby("atm_code")["demand_target"].shift(14)
    ordered["rolling_7"] = ordered.groupby("atm_code")["demand_target"].transform(lambda values: values.shift(1).rolling(7, min_periods=1).mean())
    ordered["rolling_14"] = ordered.groupby("atm_code")["demand_target"].transform(lambda values: values.shift(1).rolling(14, min_periods=1).mean())
    ordered["rolling_30"] = ordered.groupby("atm_code")["demand_target"].transform(lambda values: values.shift(1).rolling(30, min_periods=1).mean())
    ordered["transaction_count"] = ordered["transaction_count"].fillna(0)
    ordered["avg_withdrawal_amount"] = ordered["avg_withdrawal_amount"].fillna(ordered["demand_target"] / ordered["transaction_count"].replace(0, 1))
    ordered[DEFAULT_FEATURE_COLUMNS] = ordered[DEFAULT_FEATURE_COLUMNS].ffill().fillna(0)
    ordered[DEFAULT_FEATURE_COLUMNS] = ordered[DEFAULT_FEATURE_COLUMNS].fillna(0)
    ordered["target"] = ordered["demand_target"]
    return ordered.reset_index(drop=True)


def chronological_split(frame: pd.DataFrame, validation_fraction: float = 0.2, test_fraction: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if frame.empty:
        raise ValueError("Cannot split an empty dataset")

    ordered = frame.sort_values("date").reset_index(drop=True)
    dates = pd.DatetimeIndex(sorted(pd.to_datetime(ordered["date"]).dropna().unique()))
    total_dates = len(dates)
    validation_size = max(1, int(total_dates * validation_fraction))
    test_size = max(1, int(total_dates * test_fraction))
    train_end = total_dates - validation_size - test_size
    if train_end <= 0:
        raise ValueError("Dataset is too small for chronological train/validation/test splitting.")

    train = ordered[ordered["date"] <= dates[train_end - 1]].copy()
    validation = ordered[(ordered["date"] >= dates[train_end]) & (ordered["date"] <= dates[train_end + validation_size - 1])].copy()
    test = ordered[ordered["date"] >= dates[train_end + validation_size]].copy()
    return train, validation, test


def get_atm_feature_frame(atm_id: str | None = None) -> pd.DataFrame:
    dataset = build_daily_atm_dataset()
    if atm_id is not None:
        dataset = dataset[dataset["atm_code"] == atm_id]
    return create_time_series_features(dataset)


def naive_baseline(series: pd.Series) -> pd.Series:
    values = series.astype(float)
    previous_day = values.shift(1).fillna(values.iloc[0] if len(values) > 0 else 0)
    seven_day_average = values.shift(1).rolling(7, min_periods=1).mean().fillna(values.iloc[0] if len(values) > 0 else 0)
    return previous_day.combine_first(seven_day_average)
