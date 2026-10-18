from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from app.data import tinkoff_history


@pytest.fixture(scope="session", autouse=True)
def synthetic_processed_history(tmp_path_factory: pytest.TempPathFactory):
    """Provide deterministic test history without bundling private processed data."""
    fixture_dir = tmp_path_factory.mktemp("synthetic-history")
    fixture_path = fixture_dir / "atm_daily_history.csv"
    rows: list[dict[str, object]] = []
    start = date(2018, 9, 1)
    for offset in range(30):
        observed_at = start + timedelta(days=offset)
        for model_atm_id in tinkoff_history.PROTOTYPE_ATM_ID_MAP.values():
            is_missing = int(model_atm_id in {74, 85} and offset == 9)
            rows.append(
                {
                    "atm_id": model_atm_id,
                    "datetime": observed_at.isoformat(),
                    "daily_cash_flow": 0.0 if is_missing else float((model_atm_id % 11 - 5) * 100 + offset * 10),
                    "operation_count": 0 if is_missing else offset + 1,
                    "is_missing_observation": is_missing,
                }
            )
    frame = pd.DataFrame(rows)
    # Keep one genuine observed zero distinct from missing placeholders.
    frame.loc[(frame["atm_id"] == 74) & (frame["datetime"] == "2018-09-11"), "daily_cash_flow"] = 0.0
    frame.loc[(frame["atm_id"] == 74) & (frame["datetime"] == "2018-09-11"), "operation_count"] = 1
    frame.to_csv(fixture_path, index=False)

    yield fixture_path
