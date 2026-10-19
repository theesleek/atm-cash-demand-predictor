from __future__ import annotations

import csv
import hashlib
import io
import math
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.data.tinkoff_history import get_prototype_atm_mapping
from app.models.atm import ATM
from app.models.ingestion import ATMHistoryRecord, Dataset, DatasetVersion
from app.services.audit_service import AuditService


REQUIRED_COLUMNS = ("atm_id", "datetime", "operation_type", "amount")
RAW_KAGGLE_COLUMNS = frozenset({"datetime", "atm_id", "operation_value"})
PREDICTION_INPUT_COLUMNS = frozenset({"datetime", "atm_id"})
SUPPORTED_OPERATION_TYPES = frozenset({"withdrawal", "cash_withdrawal", "deposit", "cash_deposit"})
MAX_REJECTED_ROWS_IN_REPORT = 500


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)


def _fingerprint(atm_id: int, observed_at: datetime, operation_type: str, amount: float) -> str:
    value = f"{atm_id}|{observed_at.astimezone(timezone.utc).isoformat()}|{operation_type}|{amount:.8f}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _serialize(version: DatasetVersion) -> dict[str, object]:
    return {
        "dataset_id": version.dataset_id,
        "dataset_version_id": version.id,
        "version": version.version,
        "name": version.dataset.name if version.dataset else None,
        "source": version.source,
        "status": version.status,
        "uploaded_by": version.uploaded_by,
        "uploaded_at": version.uploaded_at.isoformat() if version.uploaded_at else None,
        "approved_at": version.approved_at.isoformat() if version.approved_at else None,
        "ingested_at": version.ingested_at.isoformat() if version.ingested_at else None,
        "rows_received": version.rows_received,
        "rows_accepted": version.rows_accepted,
        "rows_rejected": version.rows_rejected,
        "duplicate_rows": version.duplicate_rows,
        "date_from": version.date_from.isoformat() if version.date_from else None,
        "date_to": version.date_to.isoformat() if version.date_to else None,
        "atm_codes": version.atm_codes,
        "validation_report": version.validation_report,
    }


class IngestionService:
    def __init__(self, session: Session):
        self.session = session
        self.audit = AuditService(session)

    def validate_csv(self, content: bytes, filename: str, user_id: int) -> dict[str, object]:
        dataset = Dataset(name=filename or "uploaded.csv", source="CSV")
        self.session.add(dataset)
        self.session.flush()
        version = DatasetVersion(
            dataset_id=dataset.id,
            version=1,
            source="CSV",
            uploaded_by=user_id,
            status="UPLOADED",
            atm_codes=[],
            validation_report={},
            normalized_records=[],
        )
        self.session.add(version)
        self.session.flush()

        try:
            text = content.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text), strict=True)
            fieldnames = [field.strip() for field in (reader.fieldnames or []) if field]
            reader.fieldnames = fieldnames
        except UnicodeDecodeError:
            fieldnames = []
            reader = None
        except csv.Error:
            fieldnames = []
            reader = None

        missing_columns = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
        duplicate_columns = sorted({field for field, count in Counter(fieldnames).items() if count > 1})
        unexpected_columns = sorted(set(fieldnames) - set(REQUIRED_COLUMNS))
        schema_errors: list[str] = []
        schema_message = None
        if reader is None:
            schema_errors = ["INVALID_ENCODING_OR_CSV"]
            schema_message = "The file is not valid UTF-8 CSV data."
        elif not fieldnames:
            schema_errors = ["EMPTY_FILE"]
            schema_message = "The CSV file is empty and has no header row."
        elif duplicate_columns:
            schema_errors = ["DUPLICATE_HEADER"]
            schema_message = f"Duplicate CSV headers are not allowed: {duplicate_columns}."
        elif RAW_KAGGLE_COLUMNS.issubset(fieldnames):
            schema_errors = ["UNSUPPORTED_RAW_KAGGLE_SCHEMA"]
            schema_message = "Raw Kaggle operation files require the separate signed-flow reconstruction path; they cannot be ingested as operational history."
        elif set(fieldnames) == PREDICTION_INPUT_COLUMNS:
            schema_errors = ["PREDICTION_INPUT_NOT_SUPPORTED"]
            schema_message = "A datetime/atm_id prediction file cannot be uploaded because this application requires historical observations for forecasting."
        elif missing_columns:
            schema_errors = ["MISSING_REQUIRED_FIELD"]
            schema_message = "The operational upload requires atm_id, datetime, operation_type, and amount."
        elif unexpected_columns:
            schema_errors = ["UNSUPPORTED_COLUMNS"]
            schema_message = f"Unsupported CSV columns: {unexpected_columns}."

        if schema_errors:
            report = {
                "rows_received": 0,
                "valid_rows": 0,
                "invalid_rows": 0,
                "duplicate_rows": 0,
                "missing_timestamps": 0,
                "unknown_atm_ids": 0,
                "date_range": None,
                "rejected_rows": [{"row": 1, "reasons": schema_errors, "missing_columns": missing_columns, "unexpected_columns": unexpected_columns}],
                "schema_errors": schema_errors,
                "schema_message": schema_message,
            }
            version.status = "REJECTED"
            version.rows_rejected = 1
            version.validation_report = report
            self.session.commit()
            return _serialize(version)

        atms = {atm.atm_code: atm for atm in self.session.query(ATM).all()}
        existing_fingerprints = {
            value
            for (value,) in self.session.query(ATMHistoryRecord.record_fingerprint).all()
        }
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, object]] = []
        seen: set[str] = set()
        rows_received = 0
        duplicate_rows = 0
        missing_timestamps = 0
        unknown_atm_ids = 0
        dates: list[date] = []
        row_schema_errors: set[str] = set()

        try:
            for row_number, raw_row in enumerate(reader, start=2):
                rows_received += 1
                missing_values = [key for key, value in raw_row.items() if key is not None and value is None]
                extra_values = raw_row.get(None) or []
                if missing_values or extra_values:
                    row_schema_errors.add("INVALID_ROW_WIDTH")
                    if len(rejected) < MAX_REJECTED_ROWS_IN_REPORT:
                        rejected.append(
                            {
                                "row": row_number,
                                "reasons": ["INVALID_ROW_WIDTH"],
                                "values": {str(key).strip(): value for key, value in raw_row.items() if key is not None},
                                "missing_columns": missing_values,
                                "extra_values": extra_values,
                            }
                        )
                    continue
                row = {str(key).strip(): (value or "").strip() for key, value in raw_row.items() if key is not None}
                reasons: list[str] = []
                atm_code = row.get("atm_id", "")
                if not atm_code or not row.get("datetime") or not row.get("operation_type") or not row.get("amount"):
                    reasons.append("MISSING_REQUIRED_FIELD")
                atm = atms.get(atm_code)
                if atm is None:
                    unknown_atm_ids += 1
                    reasons.append("UNKNOWN_ATM")
                try:
                    observed_at = _parse_datetime(row.get("datetime", ""))
                except (TypeError, ValueError):
                    observed_at = None
                    missing_timestamps += 1
                    reasons.append("INVALID_DATETIME")
                operation_type = row.get("operation_type", "").lower().replace(" ", "_")
                if operation_type not in SUPPORTED_OPERATION_TYPES:
                    reasons.append("INVALID_OPERATION_TYPE")
                try:
                    amount = float(row.get("amount", ""))
                    if not math.isfinite(amount) or amount < 0:
                        raise ValueError
                except (TypeError, ValueError):
                    amount = 0.0
                    reasons.append("INVALID_AMOUNT")

                fingerprint = _fingerprint(atm.id, observed_at, operation_type, amount) if atm and observed_at else None
                if fingerprint and (fingerprint in seen or fingerprint in existing_fingerprints):
                    duplicate_rows += 1
                    reasons.append("DUPLICATE_RECORD")
                if reasons:
                    if len(rejected) < MAX_REJECTED_ROWS_IN_REPORT:
                        rejected.append({"row": row_number, "reasons": sorted(set(reasons)), "values": row})
                    continue
                seen.add(fingerprint)
                dates.append(observed_at.date())
                accepted.append(
                    {
                        "atm_code": atm_code,
                        "datetime": observed_at.astimezone(timezone.utc).isoformat(),
                        "operation_type": operation_type,
                        "amount": amount,
                        "record_fingerprint": fingerprint,
                    }
                )
        except csv.Error as exc:
            report = {
                "rows_received": rows_received,
                "valid_rows": 0,
                "invalid_rows": rows_received + 1,
                "duplicate_rows": duplicate_rows,
                "missing_timestamps": missing_timestamps,
                "unknown_atm_ids": unknown_atm_ids,
                "date_range": None,
                "rejected_rows": rejected + [{"row": rows_received + 2, "reasons": ["MALFORMED_CSV"]}],
                "schema_errors": ["MALFORMED_CSV"],
                "schema_message": f"The CSV structure is malformed: {exc}",
            }
            version.status = "REJECTED"
            version.rows_received = rows_received
            version.rows_rejected = rows_received + 1
            version.validation_report = report
            self.session.commit()
            return _serialize(version)

        report = {
            "rows_received": rows_received,
            "valid_rows": len(accepted),
            "invalid_rows": len(rejected) + max(0, rows_received - len(accepted) - len(rejected)),
            "duplicate_rows": duplicate_rows,
            "missing_timestamps": missing_timestamps,
            "unknown_atm_ids": unknown_atm_ids,
            "date_range": {"from": min(dates).isoformat(), "to": max(dates).isoformat()} if dates else None,
            "rejected_rows": rejected,
            "schema_errors": sorted(row_schema_errors),
        }
        version.status = "VALIDATED" if accepted else "REJECTED"
        version.rows_received = rows_received
        version.rows_accepted = len(accepted)
        version.rows_rejected = rows_received - len(accepted)
        version.duplicate_rows = duplicate_rows
        version.date_from = min(dates) if dates else None
        version.date_to = max(dates) if dates else None
        version.atm_codes = sorted({item["atm_code"] for item in accepted})
        version.validation_report = report
        version.normalized_records = accepted
        self.session.commit()
        self.audit.record(user_id, "DATASET_VALIDATED", "DATASET_VERSION", version.id, "WEB", {"rows_accepted": len(accepted), "rows_rejected": version.rows_rejected})
        return _serialize(version)

    def get(self, version_id: int) -> DatasetVersion | None:
        return self.session.get(DatasetVersion, version_id)

    def list(self, limit: int = 100) -> list[dict[str, object]]:
        versions = self.session.query(DatasetVersion).order_by(DatasetVersion.uploaded_at.desc()).limit(limit).all()
        return [_serialize(version) for version in versions]

    def approve(self, version_id: int, user_id: int) -> dict[str, object]:
        version = self.get(version_id)
        if version is None:
            raise ValueError("Dataset version not found")
        if version.status != "VALIDATED":
            raise ValueError(f"Dataset version cannot be approved from status {version.status}")
        version.status = "APPROVED"
        version.approved_at = _now()
        self.session.commit()
        self.audit.record(user_id, "DATASET_APPROVED", "DATASET_VERSION", version.id, "WEB")
        return _serialize(version)

    def ingest(self, version_id: int, user_id: int) -> dict[str, object]:
        version = self.get(version_id)
        if version is None:
            raise ValueError("Dataset version not found")
        if version.status != "APPROVED":
            raise ValueError(f"Dataset version cannot be ingested from status {version.status}")
        atms = {atm.atm_code: atm for atm in self.session.query(ATM).all()}
        fingerprints = [str(item["record_fingerprint"]) for item in version.normalized_records]
        if self.session.query(ATMHistoryRecord).filter(ATMHistoryRecord.record_fingerprint.in_(fingerprints)).first():
            raise ValueError("Dataset contains records already present in production history")
        try:
            for item in version.normalized_records:
                atm = atms.get(str(item["atm_code"]))
                if atm is None:
                    raise ValueError(f"Unknown ATM {item['atm_code']}")
                self.session.add(ATMHistoryRecord(
                    atm_id=atm.id,
                    dataset_version_id=version.id,
                    observed_at=_parse_datetime(str(item["datetime"])),
                    operation_type=str(item["operation_type"]),
                    amount=float(item["amount"]),
                    record_fingerprint=str(item["record_fingerprint"]),
                ))
            version.status = "INGESTED"
            version.ingested_at = _now()
            self.session.flush()
            self.audit.record(user_id, "DATASET_INGESTED", "DATASET_VERSION", version.id, "WEB", {"rows": version.rows_accepted}, commit=False)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return _serialize(version)

    def readiness(self, atm: ATM) -> dict[str, object]:
        uploaded_rows = self.session.query(ATMHistoryRecord).filter(ATMHistoryRecord.atm_id == atm.id).all()
        observed_days = len({row.observed_at.date() for row in uploaded_rows})
        latest_version = next(
            (version for version in self.session.query(DatasetVersion).order_by(DatasetVersion.uploaded_at.desc()).all() if atm.atm_code in (version.atm_codes or [])),
            None,
        )
        if observed_days < 14:
            status = "INSUFFICIENT_HISTORY"
            reason = "Insufficient history: at least 14 observed days are required for a forecast."
        elif atm.atm_code not in get_prototype_atm_mapping():
            status = "INVALID_DATA"
            reason = "The production model has no compatible identity mapping for this ATM; retraining is required."
        else:
            status = "READY"
            reason = "Sufficient valid history is available for the production forecast model."
        date_from = min((row.observed_at.date() for row in uploaded_rows), default=None)
        date_to = max((row.observed_at.date() for row in uploaded_rows), default=None)
        internal_gaps = max(0, (date_to - date_from).days + 1 - observed_days) if date_from and date_to else 0
        latest_rejected = latest_version.rows_rejected if latest_version else 0
        return {
            "atm_code": atm.atm_code,
            "history_days": observed_days,
            "status": status,
            "data_quality": "GOOD" if observed_days >= 14 else "INSUFFICIENT",
            "reason": reason,
            "rows_accepted": len(uploaded_rows),
            "rows_rejected": latest_rejected,
            "duplicate_records": latest_version.duplicate_rows if latest_version else 0,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "internal_gaps": internal_gaps,
            "missing_atm_days": internal_gaps,
            "last_ingestion_at": latest_version.ingested_at.isoformat() if latest_version and latest_version.ingested_at else None,
        }

    def uploaded_daily_history(self, atm: ATM):
        rows = self.session.query(ATMHistoryRecord).filter(ATMHistoryRecord.atm_id == atm.id).order_by(ATMHistoryRecord.observed_at.asc()).all()
        if not rows:
            return None
        import pandas as pd

        frame = pd.DataFrame([
            {
                "datetime": row.observed_at,
                "daily_cash_flow": -float(row.amount) if row.operation_type in {"withdrawal", "cash_withdrawal"} else float(row.amount),
                "operation_count": 1,
                "is_missing_observation": 0,
            }
            for row in rows
        ])
        frame["datetime"] = pd.to_datetime(frame["datetime"], utc=True)
        frame["date"] = frame["datetime"].dt.floor("D")
        return frame.groupby("date", as_index=False).agg(daily_cash_flow=("daily_cash_flow", "sum"), operation_count=("operation_count", "sum"), is_missing_observation=("is_missing_observation", "max")).rename(columns={"date": "datetime"})
