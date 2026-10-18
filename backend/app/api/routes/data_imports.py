from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import require_permission
from app.db.session import get_db
from app.models.auth import User
from app.services.ingestion_service import IngestionService


router = APIRouter(prefix="/data-imports", tags=["data-imports"])


def _service_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    return HTTPException(status_code=409 if "cannot" in message or "already" in message else 422, detail=message)


@router.post("/validate", status_code=201)
async def validate_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("data:upload", web_only=True)),
) -> dict[str, object]:
    filename = file.filename or "uploaded.csv"
    if not filename.lower().endswith(".csv") or (file.content_type and file.content_type not in {"text/csv", "application/csv", "application/vnd.ms-excel"}):
        raise HTTPException(status_code=415, detail="Only CSV uploads are supported")
    content = await file.read()
    if len(content) > settings.request_body_limit_bytes:
        raise HTTPException(status_code=413, detail="Uploaded file is too large")
    return IngestionService(db).validate_csv(content, filename, user.id)


@router.get("")
def list_imports(
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("data:upload")),
) -> list[dict[str, object]]:
    return IngestionService(db).list()


@router.get("/{version_id}")
def get_import(
    version_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("data:upload")),
) -> dict[str, object]:
    version = IngestionService(db).get(version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Dataset version not found")
    from app.services.ingestion_service import _serialize
    return _serialize(version)


@router.get("/{version_id}/rejected.csv")
def download_rejected_rows(
    version_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("data:upload")),
) -> StreamingResponse:
    version = IngestionService(db).get(version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Dataset version not found")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["row", "reasons", "values"])
    for item in version.validation_report.get("rejected_rows", []):
        writer.writerow([item.get("row"), ";".join(item.get("reasons", [])), item.get("values", {})])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="dataset-{version_id}-rejected.csv"'})


@router.post("/{version_id}/approve")
def approve_import(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("data:approve", web_only=True)),
) -> dict[str, object]:
    try:
        return IngestionService(db).approve(version_id, user.id)
    except ValueError as exc:
        raise _service_error(exc) from exc


@router.post("/{version_id}/ingest")
def ingest_import(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("data:ingest", web_only=True)),
) -> dict[str, object]:
    try:
        return IngestionService(db).ingest(version_id, user.id)
    except ValueError as exc:
        raise _service_error(exc) from exc
