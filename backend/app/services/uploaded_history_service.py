from __future__ import annotations

import pandas as pd
from sqlalchemy.orm import Session

from app.models.ingestion import ATMHistoryRecord


def load_uploaded_history(session: Session) -> pd.DataFrame | None:
    rows = session.query(ATMHistoryRecord).order_by(ATMHistoryRecord.atm_id, ATMHistoryRecord.observed_at).all()
    if not rows:
        return None

    frame = pd.DataFrame(
        [
            {
                "atm_id": row.atm_id,
                "datetime": row.observed_at,
                "daily_cash_flow": -float(row.amount)
                if row.operation_type in {"withdrawal", "cash_withdrawal"}
                else float(row.amount),
                "operation_count": 1,
                "is_missing_observation": 0,
            }
            for row in rows
        ]
    )
    frame["datetime"] = pd.to_datetime(frame["datetime"], utc=True).dt.floor("D")
    return (
        frame.groupby(["atm_id", "datetime"], as_index=False)
        .agg(
            daily_cash_flow=("daily_cash_flow", "sum"),
            operation_count=("operation_count", "sum"),
            is_missing_observation=("is_missing_observation", "max"),
        )
        .sort_values(["atm_id", "datetime"])
        .reset_index(drop=True)
    )
