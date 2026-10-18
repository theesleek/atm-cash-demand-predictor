from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATASET_PATH = PROJECT_ROOT / "data" / "synthetic" / "sample_atm_data.csv"


def load_atm_dataframe() -> pd.DataFrame:
    dataframe = pd.read_csv(DATASET_PATH)
    dataframe["current_cash"] = pd.to_numeric(dataframe["current_cash"], errors="coerce")
    dataframe["daily_demand"] = pd.to_numeric(dataframe["daily_demand"], errors="coerce")
    dataframe["capacity"] = pd.to_numeric(dataframe["capacity"], errors="coerce")
    return dataframe.fillna({"status": "active"})


def get_atm_records() -> list[dict[str, object]]:
    dataframe = load_atm_dataframe()
    return dataframe.to_dict(orient="records")


def get_atm_by_id(atm_id: str) -> dict[str, object] | None:
    for record in get_atm_records():
        if record.get("atm_code") == atm_id:
            return record
    return None


def get_dashboard_summary() -> dict[str, object]:
    dataframe = load_atm_dataframe()
    critical_alerts = int((dataframe["current_cash"] < dataframe["daily_demand"] * 0.5).sum())
    warning_alerts = int((dataframe["current_cash"] < dataframe["daily_demand"] * 0.75).sum())
    avg_cash_buffer = float((dataframe["capacity"] - dataframe["current_cash"]).mean())

    return {
        "atms_monitored": int(len(dataframe)),
        "critical_alerts": critical_alerts,
        "warning_alerts": warning_alerts,
        "avg_cash_buffer": round(avg_cash_buffer, 2),
        "total_capacity": float(dataframe["capacity"].sum()),
    }
