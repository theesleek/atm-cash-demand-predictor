from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.data.tinkoff_history import get_history_processing_report, load_tinkoff_history
from app.services.uploaded_history_service import load_uploaded_history


def _unavailable_report(reason: str, source: str) -> dict[str, object]:
    return {
        "status": "UNAVAILABLE",
        "reason": reason,
        "source": source,
        "total_processed_rows": 0,
        "atm_count": 0,
        "date_range": None,
        "expected_atm_days": 0,
        "observed_atm_days": 0,
        "unobserved_atm_days": 0,
        "internally_imputed_observations": 0,
        "pre_imputation_observed_atm_days": 0,
        "pre_imputation_unobserved_atm_days": 0,
        "actual_atm_days": 0,
        "missing_atm_days": 0,
        "internal_missing_atm_days": 0,
        "filled_observations": 0,
        "final_processed_rows": 0,
        "missing_rate": 0.0,
        "ingestion": None,
    }


def _uploaded_ingestion_summary(history: pd.DataFrame) -> dict[str, object]:
    return {
        "source": "uploaded_database",
        "rows_received": int(len(history)),
        "rows_accepted": int(len(history)),
        "rows_rejected": 0,
        "duplicates": 0,
        "missing_observations": int(history["is_missing_observation"].sum()),
        "invalid_dates": 0,
        "invalid_atm_identifiers": 0,
        "negative_value_candidates": int((history["daily_cash_flow"] < 0).sum()),
        "dataset_version": "database:uploaded-history",
    }


def get_data_quality_report(
    *,
    session: Session | None = None,
    history_path: Path | None = None,
) -> dict[str, object]:
    if history_path is not None:
        history = load_tinkoff_history(history_path)
        ingestion = get_history_processing_report(history_path)
        source = "explicit_local_file"
    elif session is not None:
        history = load_uploaded_history(session)
        if history is None:
            return _unavailable_report("No uploaded operational history is available.", "uploaded_database")
        ingestion = _uploaded_ingestion_summary(history)
        source = "uploaded_database"
    else:
        return _unavailable_report("No uploaded operational history is available.", "uploaded_database")
    if history.empty:
        return _unavailable_report("The selected history source contains no records.", source)

    dates = history["datetime"].dt.normalize()
    atm_count = int(history["atm_id"].nunique())
    date_min = dates.min()
    date_max = dates.max()
    calendar_days = int((date_max - date_min).days) + 1
    expected_atm_days = atm_count * calendar_days
    observed_atm_days = int(history[["atm_id", "datetime"]].drop_duplicates().shape[0])
    unobserved_atm_days = max(expected_atm_days - observed_atm_days, 0)
    internally_imputed_observations = int(history["is_missing_observation"].sum())
    pre_imputation_observed_atm_days = int((history["is_missing_observation"] == 0).sum())
    pre_imputation_unobserved_atm_days = max(expected_atm_days - pre_imputation_observed_atm_days, 0)
    missing_rate = unobserved_atm_days / expected_atm_days if expected_atm_days else 0.0
    status = "GOOD" if missing_rate == 0 and internally_imputed_observations == 0 else "ATTENTION"
    return {
        "status": status,
        "reason": "The processed history contains unobserved ATM-days or internally imputed observations." if status == "ATTENTION" else "The processed history is complete.",
        "source": source,
        "definition": "Observed ATM-days are unique ATM/date rows present in the selected history source. Unobserved ATM-days are expected ATM/date pairs absent from that source. Internally imputed observations are present rows flagged by is_missing_observation=1.",
        "total_raw_records": None,
        "total_processed_rows": int(len(history)),
        "atm_count": atm_count,
        "date_range": {"from": date_min.date().isoformat(), "to": date_max.date().isoformat()},
        "expected_atm_days": expected_atm_days,
        "observed_atm_days": observed_atm_days,
        "unobserved_atm_days": unobserved_atm_days,
        "internally_imputed_observations": internally_imputed_observations,
        "pre_imputation_observed_atm_days": pre_imputation_observed_atm_days,
        "pre_imputation_unobserved_atm_days": pre_imputation_unobserved_atm_days,
        # Compatibility aliases for existing consumers of the Phase 22 response.
        "actual_atm_days": observed_atm_days,
        "missing_atm_days": unobserved_atm_days,
        "internal_missing_atm_days": internally_imputed_observations,
        "filled_observations": internally_imputed_observations,
        "final_processed_rows": int(len(history)),
        "missing_rate": round(missing_rate, 6),
        "ingestion": ingestion,
    }
