"""名單匯入 API（F-IMP-1 ~ F-IMP-4）。

管理員上傳整理好的 CSV / XLSX：POST /imports（multipart）→ 預覽；POST /imports/{id}/commit 確認。
（F-IMP-5 API 匯入已在 2026-11-18 移除：沒有模型，名單一律從檔案匯入。）
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
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
    funnel: dict[str, int] | None = None


class BatchDetail(BatchSummary):
    rows_skipped: int  # 網址 invalid、不進名單的列（SPEC 8.4）
    rows: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]]  # 不擋匯入的提示：看不懂的欄位、沒有資料來源欄


def _detail(batch: ImportBatch) -> BatchDetail:
    summary = BatchSummary.model_validate(batch).model_dump()
    payload = batch.payload or []
    report = batch.error_report or []
    return BatchDetail(
        **summary,
        rows_skipped=sum(r.get("action") == "skip" for r in payload),
        rows=payload[: importer.PREVIEW_ROW_LIMIT],
        errors=[e for e in report if e.get("level") != "warning"],
        warnings=[{k: v for k, v in e.items() if k != "level"} for e in report if e.get("level") == "warning"],
    )


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
    table = importer.read_table(content, file.filename or "")
    records: list[dict[str, Any]] = [{str(k): v for k, v in r.items()} for r in table.df.to_dict("records")]
    parsed = importer.normalize(
        records,
        importer.industry_lookup(db),
        unknown_columns=table.unknown_columns,
        has_source_column="source" in table.df.columns,
    )
    batch = importer.create_batch(
        db,
        parsed,
        file_name=file.filename,
        source="csv" if (file.filename or "").lower().endswith(".csv") else "xlsx",
        model_name=model_name,
        user=user,
    )
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
