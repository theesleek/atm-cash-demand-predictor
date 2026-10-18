from __future__ import annotations

import json
import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
HISTORY_PATH = Path(
    os.getenv(
        "ATM_DAILY_HISTORY_PATH",
        str(PROJECT_ROOT / "data" / "processed" / "atm_daily_history.csv"),
    )
)

# Prototype-only pairing. Replace these values with an approved ATM identity map.
PROTOTYPE_ATM_ID_MAP: dict[str, int] = {
    "ATM-001": 74,
    "ATM-002": 85,
    "ATM-003": 86,
    "ATM-004": 87,
    "ATM-005": 88,
    "ATM-006": 90,
    "ATM-007": 91,
    "ATM-008": 93,
    "ATM-009": 94,
    "ATM-010": 96,
    "ATM-011": 97,
    "ATM-012": 98,
    "ATM-013": 99,
    "ATM-014": 100,
    "ATM-015": 101,
    "ATM-016": 102,
    "ATM-017": 103,
    "ATM-018": 104,
    "ATM-019": 105,
    "ATM-020": 106,
}

REQUIRED_HISTORY_COLUMNS = {
    "atm_id",
    "datetime",
    "daily_cash_flow",
    "operation_count",
    "is_missing_observation",
}

REQUIRED_RAW_OPERATION_COLUMNS = {
    "atm_id",
    "datetime",
    "operation_value",
}


def reconstruct_tinkoff_signed_daily_flow(path: Path) -> pd.DataFrame:
    """Aggregate the official training-file target without assigning operation semantics.

    The Kaggle competition describes its target as the sum of all operation values
    for each ATM-day.  This function deliberately retains every valid raw row,
    including duplicate records, because the verified processed history's
    ``operation_count`` is the raw row count.  It does not infer withdrawal,
    deposit, currency, timezone, or operation-type semantics.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Tinkoff raw operation history not found: {path}")

    raw = pd.read_csv(path)
    missing_columns = REQUIRED_RAW_OPERATION_COLUMNS.difference(raw.columns)
    if missing_columns:
        raise ValueError(f"Tinkoff raw operation history is missing columns: {sorted(missing_columns)}")

    normalized = raw[list(REQUIRED_RAW_OPERATION_COLUMNS)].copy()
    normalized["datetime"] = pd.to_datetime(normalized["datetime"], errors="coerce")
    normalized["atm_id"] = pd.to_numeric(normalized["atm_id"], errors="coerce")
    normalized["operation_value"] = pd.to_numeric(normalized["operation_value"], errors="coerce")
    valid = normalized.dropna(subset=list(REQUIRED_RAW_OPERATION_COLUMNS)).copy()
    valid["atm_id"] = valid["atm_id"].astype(int)
    valid["datetime"] = valid["datetime"].dt.normalize()

    return (
        valid.groupby(["atm_id", "datetime"], as_index=False)
        .agg(
            daily_cash_flow=("operation_value", "sum"),
            operation_count=("operation_value", "size"),
        )
        .sort_values(["atm_id", "datetime"])
        .reset_index(drop=True)
    )


def build_calendar_aligned_tinkoff_feature_frame(history: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Build leakage-safe ATM features with an observed target exactly one day ahead.

    A processed row marked ``is_missing_observation`` is an explicit placeholder,
    not a zero-flow observation. It is excluded as both a feature source and a
    target. Candidate forecast rows are also excluded when their next calendar
    day is absent from the processed file. No values are reindexed into the
    dataset as observed cash flow.
    """
    missing_columns = REQUIRED_HISTORY_COLUMNS.difference(history.columns)
    if missing_columns:
        raise ValueError(f"Tinkoff history is missing columns: {sorted(missing_columns)}")

    normalized = history[list(REQUIRED_HISTORY_COLUMNS)].copy()
    normalized["datetime"] = pd.to_datetime(normalized["datetime"], errors="coerce").dt.normalize()
    for column in ("atm_id", "daily_cash_flow", "operation_count", "is_missing_observation"):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized = normalized.dropna(subset=list(REQUIRED_HISTORY_COLUMNS)).copy()
    normalized["atm_id"] = normalized["atm_id"].astype(int)
    if normalized.duplicated(["atm_id", "datetime"]).any():
        raise ValueError("Tinkoff history contains duplicate ATM/date rows")

    frames: list[pd.DataFrame] = []
    alignment = {
        "source_rows": int(len(normalized)),
        "source_missing_placeholders": int((normalized["is_missing_observation"] == 1).sum()),
        "eligible_source_rows": 0,
        "excluded_next_date_absent": 0,
        "excluded_next_date_missing_placeholder": 0,
        "valid_target_rows": 0,
    }
    for atm_id, group in normalized.groupby("atm_id", sort=False):
        group = group.sort_values("datetime").set_index("datetime")
        # Add one terminal day so the final observed day is explicitly counted
        # as having no next-calendar-day target.
        calendar = pd.date_range(group.index.min(), group.index.max() + pd.Timedelta(days=1), freq="D")
        daily = group.reindex(calendar)
        daily.index.name = "datetime"
        daily["atm_id"] = int(atm_id)
        has_record = daily["daily_cash_flow"].notna()
        observed = has_record & daily["is_missing_observation"].eq(0)
        flow = daily["daily_cash_flow"].where(observed).astype(float)
        operations = daily["operation_count"].where(observed).astype(float)
        next_has_record = has_record.shift(-1, fill_value=False)
        next_observed = observed.shift(-1, fill_value=False)

        alignment["eligible_source_rows"] += int(observed.sum())
        alignment["excluded_next_date_absent"] += int((observed & ~next_has_record).sum())
        alignment["excluded_next_date_missing_placeholder"] += int((observed & next_has_record & ~next_observed).sum())

        daily["day_of_week"] = daily.index.dayofweek
        daily["is_weekend"] = (daily.index.dayofweek >= 5).astype(int)
        daily["day_of_month"] = daily.index.day
        daily["month"] = daily.index.month
        daily["week_of_year"] = daily.index.isocalendar().week.astype(int)
        daily["is_month_end"] = daily.index.is_month_end.astype(int)
        # Calendar-grid shifts preserve their declared day horizons; absent
        # earlier dates stay NaN rather than borrowing a later/earlier row.
        daily["lag_1"] = flow.shift(1)
        daily["lag_7"] = flow.shift(7)
        daily["lag_14"] = flow.shift(14)
        daily["rolling_7"] = flow.shift(1).rolling(7, min_periods=1).mean()
        daily["rolling_14"] = flow.shift(1).rolling(14, min_periods=1).mean()
        daily["rolling_30"] = flow.shift(1).rolling(30, min_periods=1).mean()
        daily["operation_count"] = operations
        daily["operation_count_lag_1"] = operations.shift(1)
        daily["operation_count_rolling_7"] = operations.shift(1).rolling(7, min_periods=1).mean()
        daily["is_missing_observation"] = daily["is_missing_observation"].where(has_record, 1).astype(int)
        daily["target"] = flow.shift(-1)
        daily["forecast_date"] = daily.index + pd.Timedelta(days=1)
        daily["historical_mean"] = flow.expanding().mean()
        frames.append(daily.loc[observed & next_observed].reset_index())

    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not frame.empty:
        frame = frame.sort_values(["forecast_date", "atm_id"]).reset_index(drop=True)
        frame["date"] = frame["forecast_date"]
    alignment["valid_target_rows"] = int(len(frame))
    return frame, alignment


def get_history_processing_report(path: Path | None = None) -> dict[str, object]:
    history_path = path or HISTORY_PATH
    if not history_path.is_file():
        raise FileNotFoundError(f"Tinkoff daily history not found: {history_path}")
    raw = pd.read_csv(history_path)
    missing_columns = REQUIRED_HISTORY_COLUMNS.difference(raw.columns)
    if missing_columns:
        raise ValueError(f"Tinkoff daily history is missing columns: {sorted(missing_columns)}")
    normalized = raw[list(REQUIRED_HISTORY_COLUMNS)].copy()
    normalized["datetime"] = pd.to_datetime(normalized["datetime"], errors="coerce")
    for column in ("atm_id", "daily_cash_flow", "operation_count", "is_missing_observation"):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    invalid_mask = normalized[list(REQUIRED_HISTORY_COLUMNS)].isna().any(axis=1)
    valid = normalized.loc[~invalid_mask].copy()
    duplicate_count = int(valid.duplicated(["atm_id", "datetime"], keep="last").sum())
    accepted = valid.drop_duplicates(["atm_id", "datetime"], keep="last")
    source_hash = hashlib.sha256(history_path.read_bytes()).hexdigest()
    return {
        "source": str(history_path.relative_to(PROJECT_ROOT)) if history_path.is_relative_to(PROJECT_ROOT) else history_path.name,
        "rows_received": int(len(raw)),
        "rows_accepted": int(len(accepted)),
        "rows_rejected": int(invalid_mask.sum()),
        "duplicates": duplicate_count,
        "missing_observations": int(accepted["is_missing_observation"].sum()),
        "invalid_dates": int(normalized["datetime"].isna().sum()),
        "invalid_atm_identifiers": int((normalized["atm_id"].isna() | (normalized["atm_id"] <= 0)).sum()),
        "negative_value_candidates": int(((normalized["daily_cash_flow"] < 0) | (normalized["operation_count"] < 0)).sum()),
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": f"sha256:{source_hash}",
    }


def get_prototype_atm_mapping() -> dict[str, int]:
    configured_mapping = os.getenv("PROTOTYPE_ATM_ID_MAP")
    if not configured_mapping:
        return PROTOTYPE_ATM_ID_MAP.copy()

    try:
        parsed_mapping = json.loads(configured_mapping)
        if not isinstance(parsed_mapping, dict):
            raise ValueError("mapping must be a JSON object")
        return {str(atm_code): int(tinkoff_id) for atm_code, tinkoff_id in parsed_mapping.items()}
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("PROTOTYPE_ATM_ID_MAP must be a JSON object of ATM codes to integer IDs") from exc


def load_tinkoff_history(path: Path | None = None) -> pd.DataFrame:
    history_path = path or HISTORY_PATH
    if not history_path.is_file():
        raise FileNotFoundError(f"Tinkoff daily history not found: {history_path}")

    history = pd.read_csv(history_path)
    missing_columns = REQUIRED_HISTORY_COLUMNS.difference(history.columns)
    if missing_columns:
        raise ValueError(f"Tinkoff daily history is missing columns: {sorted(missing_columns)}")

    history = history[list(REQUIRED_HISTORY_COLUMNS)].copy()
    history["datetime"] = pd.to_datetime(history["datetime"], errors="coerce")
    for column in ("atm_id", "daily_cash_flow", "operation_count", "is_missing_observation"):
        history[column] = pd.to_numeric(history[column], errors="coerce")

    history = history.dropna(subset=list(REQUIRED_HISTORY_COLUMNS)).copy()
    history["atm_id"] = history["atm_id"].astype(int)
    history["is_missing_observation"] = history["is_missing_observation"].astype(int)
    history = history.sort_values(["atm_id", "datetime"])
    return history.drop_duplicates(["atm_id", "datetime"], keep="last").reset_index(drop=True)


def build_tinkoff_feature_row(
    application_atm_id: str,
    feature_names: list[str],
    history_path: Path | None = None,
) -> tuple[pd.DataFrame, str]:
    mapping = get_prototype_atm_mapping()
    if application_atm_id not in mapping:
        raise ValueError(f"ATM {application_atm_id} has no prototype Tinkoff mapping")

    tinkoff_atm_id = mapping[application_atm_id]
    history = load_tinkoff_history(history_path)
    atm_history = history[history["atm_id"] == tinkoff_atm_id].reset_index(drop=True)
    if atm_history.empty:
        raise ValueError(f"No Tinkoff history for mapped ATM ID {tinkoff_atm_id}")
    if len(atm_history) < 14:
        raise ValueError(f"At least 14 history rows are required for ATM {application_atm_id}")

    return build_feature_row_from_history(application_atm_id, feature_names, atm_history, tinkoff_atm_id)


def build_feature_row_from_history(
    application_atm_id: str,
    feature_names: list[str],
    atm_history: pd.DataFrame,
    model_atm_id: int,
) -> tuple[pd.DataFrame, str]:
    if len(atm_history) < 14:
        raise ValueError(f"At least 14 history rows are required for ATM {application_atm_id}")
    last_date = pd.Timestamp(atm_history["datetime"].iloc[-1])
    forecast_day = last_date + timedelta(days=1)
    cash_flow = atm_history["daily_cash_flow"].astype(float)
    operations = atm_history["operation_count"].astype(float)
    values: dict[str, float | int] = {
        "atm_id": model_atm_id,
        "operation_count": float(operations.iloc[-1]),
        "is_missing_observation": int(atm_history["is_missing_observation"].iloc[-1]),
        "day_of_week": int(forecast_day.dayofweek),
        "is_weekend": int(forecast_day.dayofweek >= 5),
        "day_of_month": int(forecast_day.day),
        "month": int(forecast_day.month),
        "week_of_year": int(forecast_day.isocalendar().week),
        "is_month_end": int(forecast_day.is_month_end),
        "lag_1": float(cash_flow.iloc[-1]),
        "lag_7": float(cash_flow.iloc[-7]),
        "lag_14": float(cash_flow.iloc[-14]),
        "rolling_7": float(cash_flow.tail(7).mean()),
        "rolling_14": float(cash_flow.tail(14).mean()),
        "rolling_30": float(cash_flow.tail(30).mean()),
        "operation_count_lag_1": float(operations.iloc[-1]),
        "operation_count_rolling_7": float(operations.tail(7).mean()),
    }
    unknown_features = [name for name in feature_names if name not in values]
    if unknown_features:
        raise ValueError(f"Unsupported configured model features: {unknown_features}")

    features = pd.DataFrame([[values[name] for name in feature_names]], columns=feature_names)
    return features, forecast_day.date().isoformat()
