"""名單匯入 API（F-IMP-1 ~ F-IMP-5）。

- 管理員上傳檔案：POST /imports（multipart）→ 預覽；POST /imports/{id}/commit 確認。
- MLE function：POST /imports/api（JSON + X-API-Key），可帶 ?commit=true 直接寫入。
"""

import secrets
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.config import Settings, get_settings
from app.db import get_db
from app.errors import AppError
from app.models import AppUser, ImportBatch
from app.services import importer

router = APIRouter()


class BatchSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    batch_id: int
    file_name: str | None
    source: str
    status: str
    model_name: str | None
    run_id: int | None
    rows_total: int
    rows_created: int
    rows_updated: int
    rows_unchanged: int
    rows_error: int
    created_at: datetime


class BatchDetail(BatchSummary):
    rows: list[dict[str, Any]]
    errors: list[dict[str, Any]]


class ApiImportRow(BaseModel):
    tax_id: str
    name: str
    website_url: str | None = None
    registered_products: str | None = None
    industry: str | None = None
    customer_type: str | None = None
    likelihood: str | None = None
    priority: str
    score: float | None = None
    reason: str | None = None


class ApiImportBody(BaseModel):
    model_name: str = Field(min_length=1, max_length=200)
    rows: list[ApiImportRow] = Field(min_length=1, max_length=20000)


def _detail(batch: ImportBatch) -> BatchDetail:
    summary = BatchSummary.model_validate(batch).model_dump()
    rows = (batch.payload or [])[: importer.PREVIEW_ROW_LIMIT]
    return BatchDetail(**summary, rows=rows, errors=batch.error_report or [])


def _get_batch(db: Session, batch_id: int) -> ImportBatch:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise AppError("IMPORT_NOT_FOUND", "找不到這個匯入批次", 404)
    return batch


@router.post("/imports", response_model=BatchDetail, status_code=201)
async def upload_import(
    file: UploadFile = File(...),
    model_name: str | None = Form(default=None),
    user: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> BatchDetail:
    content = await file.read(importer.MAX_FILE_BYTES + 1)
    df = importer.read_table(content, file.filename or "")
    records: list[dict[str, Any]] = [{str(k): v for k, v in r.items()} for r in df.to_dict("records")]
    parsed = importer.normalize(records, importer.industry_lookup(db))
    batch = importer.create_batch(
        db,
        parsed,
        file_name=file.filename,
        source="csv" if (file.filename or "").lower().endswith(".csv") else "xlsx",
        model_name=model_name,
        user=user,
    )
    return _detail(batch)


@router.post("/imports/api", response_model=BatchDetail, status_code=201)
def api_import(
    body: ApiImportBody,
    commit: bool = Query(default=False),
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> BatchDetail:
    if not settings.import_api_key or not x_api_key or not secrets.compare_digest(x_api_key, settings.import_api_key):
        raise AppError("INVALID_API_KEY", "API key 不正確", 401)
    records = [r.model_dump() for r in body.rows]
    parsed = importer.normalize(records, importer.industry_lookup(db))
    batch = importer.create_batch(db, parsed, file_name=None, source="api", model_name=body.model_name, user=None)
    if commit:
        if parsed.errors:
            raise AppError("IMPORT_HAS_ERRORS", "資料有錯誤，未寫入；請修正後重送", 422, parsed.errors)
        batch = importer.commit_batch(db, batch, None)
    return _detail(batch)


@router.get("/imports", response_model=list[BatchSummary])
def list_imports(_: AppUser = Depends(require_admin), db: Session = Depends(get_db)) -> list[ImportBatch]:
    return list(db.scalars(select(ImportBatch).order_by(ImportBatch.batch_id.desc()).limit(50)))


@router.get("/imports/{batch_id}", response_model=BatchDetail)
def get_import(batch_id: int, _: AppUser = Depends(require_admin), db: Session = Depends(get_db)) -> BatchDetail:
    return _detail(_get_batch(db, batch_id))


@router.post("/imports/{batch_id}/commit", response_model=BatchDetail)
def commit_import(batch_id: int, user: AppUser = Depends(require_admin), db: Session = Depends(get_db)) -> BatchDetail:
    return _detail(importer.commit_batch(db, _get_batch(db, batch_id), user))


@router.post("/imports/{batch_id}/cancel", response_model=BatchDetail)
def cancel_import(batch_id: int, _: AppUser = Depends(require_admin), db: Session = Depends(get_db)) -> BatchDetail:
    return _detail(importer.cancel_batch(db, _get_batch(db, batch_id)))
