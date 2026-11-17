"""名單匯入：解析 → 驗證 → 預覽差異 → 確認後寫入（SPEC 4.1、8.3）。

流程：
1. read_table()：讀 CSV（UTF-8 或 Big5）或 XLSX。XLSX 有多個工作表時，挑有「優先級」欄位的那張當主表；
   主表沒有統編的話，用公司名稱到其他工作表找統編與登記產品（現有 Excel 就是這樣分兩張表）。
2. normalize()：欄位名稱對應、清理、驗證，產出乾淨的資料列與錯誤清單。
3. build_preview()：和資料庫比對，每列標記 create / update / unchanged。
4. commit_batch()：建立 model_run，寫入公司與新版分類，舊版分類 is_current 改成 false。
"""

import io
import math
import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import ActivityLog, AppUser, Classification, Company, DimIndustry, ImportBatch, ModelRun

MAX_FILE_BYTES = 10 * 1024 * 1024
PREVIEW_ROW_LIMIT = 500

# 標準欄位 → 可接受的表頭（中文 Excel 表頭或英文欄名）
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "tax_id": ("統編", "統一編號", "tax_id"),
    "name": ("公司名稱", "name", "company_name"),
    "website_url": ("官網", "官網(工具找到的)", "website", "website_url"),
    "registered_products": ("工廠主要產品(登記)", "登記產品", "registered_products"),
    "industry": ("產業", "industry"),
    "customer_type": ("客戶屬性", "customer_type"),
    "likelihood": ("端子台使用可能性", "使用可能性", "likelihood"),
    "priority": ("優先級", "priority"),
    "score": ("分數", "score"),
    "reason": ("判斷理由", "reason"),
}
# 這些欄位是圖例、人工標註或可推導的值，不匯入（SPEC 8.3）
IGNORED_COLUMNS = {"序號", "建議動作", "分類", "家數", "標準化產業", "是否真的潛在客戶(Y/N)", "業務備註"}

NO_WEBSITE = {"", "無", "無官網", "-", "n/a", "na", "none"}
LIKELIHOOD_MAP = {"高": ("高", False), "中": ("中", False), "低": ("低", False), "明確但競合": ("高", True)}
COMPARED_FIELDS = (
    "name",
    "website_url",
    "registered_products",
    "industry_id",
    "customer_type",
    "likelihood",
    "is_competitor",
    "priority",
    "score",
    "reason",
)


@dataclass
class ParsedFile:
    rows: list[dict[str, Any]]
    errors: list[dict[str, Any]] = field(default_factory=list)


# ---------- 1. 讀檔 ----------
def _rename(df: pd.DataFrame) -> pd.DataFrame:
    lookup = {alias.strip().lower(): key for key, aliases in COLUMN_ALIASES.items() for alias in aliases}
    renamed: dict[str, str] = {}
    for col in df.columns:
        key = lookup.get(str(col).strip().lower())
        if key and key not in renamed.values():
            renamed[col] = key
    keep = list(renamed)
    return df[keep].rename(columns=renamed)


def _decode_csv(content: bytes) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "cp950"):
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    raise AppError("IMPORT_DECODE_FAILED", "無法讀取檔案編碼，請存成 UTF-8 或 Big5 的 CSV", 400)


def _read_xlsx(content: bytes) -> pd.DataFrame:
    try:
        sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, dtype=str, keep_default_na=False)
    except Exception as exc:  # openpyxl 對壞檔會丟各種例外
        raise AppError("IMPORT_BAD_FILE", "無法開啟這個 Excel 檔", 400) from exc
    frames = {name: _rename(df) for name, df in sheets.items()}
    main_name = next((n for n, df in frames.items() if "priority" in df.columns), None)
    if main_name is None:
        raise AppError("IMPORT_NO_PRIORITY", "找不到含「優先級」欄位的工作表", 400)
    main = frames[main_name]
    if "tax_id" not in main.columns:
        ref = next((df for n, df in frames.items() if n != main_name and {"tax_id", "name"} <= set(df.columns)), None)
        if ref is not None:
            extra = [c for c in ("tax_id", "registered_products") if c in ref.columns and c not in main.columns]
            lookup = ref[["name", *extra]].drop_duplicates("name")
            main = main.merge(lookup, on="name", how="left")
    return main


def read_table(content: bytes, filename: str) -> pd.DataFrame:
    if len(content) > MAX_FILE_BYTES:
        raise AppError("IMPORT_FILE_TOO_LARGE", "檔案超過 10 MB", 413)
    lower = filename.lower()
    if lower.endswith((".xlsx", ".xlsm")):
        df = _read_xlsx(content)
    elif lower.endswith(".csv"):
        df = _rename(_decode_csv(content))
    else:
        raise AppError("IMPORT_UNSUPPORTED_TYPE", "只支援 .csv 或 .xlsx", 400)
    return df.fillna("")


# ---------- 2. 清理與驗證 ----------
def _clean(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def _tax_id(raw: str) -> str | None:
    digits = re.sub(r"\.0+$", "", raw).strip()
    if not digits.isdigit() or not 1 <= len(digits) <= 8:
        return None
    return digits.zfill(8)


def normalize(records: list[dict[str, Any]], industries: dict[str, int]) -> ParsedFile:
    """records 的 key 是標準欄位名。回傳乾淨資料列與錯誤（row 是 Excel 上看到的列號，表頭是第 1 列）。"""
    parsed = ParsedFile(rows=[])
    seen: dict[str, int] = {}
    for i, rec in enumerate(records):
        row_no = i + 2

        def get(k: str, rec: dict[str, Any] = rec) -> str:
            return _clean(rec.get(k))

        errs: list[tuple[str, str]] = []

        name = get("name")
        if not name:
            errs.append(("name", "缺少公司名稱"))
        tax_id = _tax_id(get("tax_id"))
        if tax_id is None:
            errs.append(("tax_id", f"統編必須是 8 碼數字（目前是「{get('tax_id')}」）"))
        elif tax_id in seen:
            errs.append(("tax_id", f"統編 {tax_id} 和第 {seen[tax_id]} 列重複"))

        industry_id: int | None = None
        if get("industry"):
            industry_id = industries.get(get("industry"))
            if industry_id is None:
                errs.append(("industry", f"產業「{get('industry')}」不在 19 類產業清單裡"))

        likelihood: str | None = None
        is_competitor = False
        if get("likelihood"):
            mapped = LIKELIHOOD_MAP.get(get("likelihood"))
            if mapped is None:
                errs.append(("likelihood", f"使用可能性只能是 高／中／低／明確但競合（目前是「{get('likelihood')}」）"))
            else:
                likelihood, is_competitor = mapped

        priority = get("priority").upper()
        if priority not in {"A", "B", "C", "D"}:
            errs.append(("priority", f"優先級只能是 A–D（目前是「{get('priority')}」）"))

        score: float | None = None
        if get("score"):
            try:
                score = float(get("score"))
                if not 0 <= score <= 100:
                    raise ValueError
            except ValueError:
                errs.append(("score", "分數必須是 0–100 的數字"))

        if errs:
            parsed.errors.extend({"row": row_no, "field": f, "message": m} for f, m in errs)
            continue
        assert tax_id is not None
        seen[tax_id] = row_no
        website = get("website_url")
        parsed.rows.append(
            {
                "row": row_no,
                "tax_id": tax_id,
                "name": name,
                "website_url": None if website.lower() in NO_WEBSITE else website,
                "registered_products": get("registered_products") or None,
                "industry_id": industry_id,
                "customer_type": get("customer_type") or None,
                "likelihood": likelihood,
                "is_competitor": is_competitor,
                "priority": priority,
                "score": score,
                "reason": get("reason") or None,
            }
        )
    return parsed


def industry_lookup(db: Session) -> dict[str, int]:
    return {i.name: i.industry_id for i in db.scalars(select(DimIndustry))}


# ---------- 3. 預覽 ----------
def _current_state(db: Session, tax_ids: list[str]) -> dict[str, dict[str, Any]]:
    stmt = (
        select(Company, Classification)
        .outerjoin(Classification, (Classification.company_id == Company.company_id) & Classification.is_current)
        .where(Company.tax_id.in_(tax_ids))
    )
    state: dict[str, dict[str, Any]] = {}
    for company, cl in db.execute(stmt):
        state[company.tax_id] = {
            "name": company.name,
            "website_url": company.website_url,
            "registered_products": company.registered_products,
            "industry_id": cl.industry_id if cl else None,
            "customer_type": cl.customer_type if cl else None,
            "likelihood": cl.likelihood if cl else None,
            "is_competitor": cl.is_competitor if cl else False,
            "priority": cl.priority if cl else None,
            "score": float(cl.score) if cl and cl.score is not None else None,
            "reason": cl.reason if cl else None,
            "website_verified": company.website_verified,
        }
    return state


def build_preview(db: Session, parsed: ParsedFile) -> list[dict[str, Any]]:
    state = _current_state(db, [r["tax_id"] for r in parsed.rows])
    for row in parsed.rows:
        old = state.get(row["tax_id"])
        if old is None:
            row["action"] = "create"
            continue
        if old["website_verified"]:
            row["website_url"] = old["website_url"]  # 業務確認過的官網不被模型覆蓋
        changed = [
            f for f in COMPARED_FIELDS if row[f] != old[f] and not (f == "website_url" and old["website_verified"])
        ]
        row["action"] = "update" if changed else "unchanged"
        row["changed_fields"] = changed
    return parsed.rows


def create_batch(
    db: Session,
    parsed: ParsedFile,
    *,
    file_name: str | None,
    source: str,
    model_name: str | None,
    user: AppUser | None,
) -> ImportBatch:
    rows = build_preview(db, parsed)
    batch = ImportBatch(
        file_name=file_name,
        source=source,
        model_name=model_name,
        rows_total=len(rows) + len({e["row"] for e in parsed.errors}),
        rows_created=sum(r["action"] == "create" for r in rows),
        rows_updated=sum(r["action"] == "update" for r in rows),
        rows_unchanged=sum(r["action"] == "unchanged" for r in rows),
        rows_error=len({e["row"] for e in parsed.errors}),
        payload=rows,
        error_report=parsed.errors,
        imported_by=user.user_id if user else None,
        status="previewed",
    )
    db.add(batch)
    db.commit()
    return batch


# ---------- 4. 確認寫入 ----------
def commit_batch(db: Session, batch: ImportBatch, user: AppUser | None) -> ImportBatch:
    if batch.status != "previewed":
        raise AppError("IMPORT_NOT_PREVIEWED", "這個匯入批次已經確認或取消過了", 409)
    # 預覽之後資料庫可能又變了，確認時重新比對一次
    rows = build_preview(db, ParsedFile(rows=[dict(r) for r in batch.payload]))
    to_write = [r for r in rows if r["action"] != "unchanged"]

    run: ModelRun | None = None
    if to_write:
        run = ModelRun(model_name=batch.model_name or f"import-batch-{batch.batch_id}")
        db.add(run)
        db.flush()

    existing = {
        c.tax_id: c for c in db.scalars(select(Company).where(Company.tax_id.in_([r["tax_id"] for r in to_write])))
    }
    for r in to_write:
        company = existing.get(r["tax_id"])
        if company is None:
            company = Company(
                tax_id=r["tax_id"],
                name=r["name"],
                website_url=r["website_url"],
                registered_products=r["registered_products"],
                status="pending_review",
                first_batch_id=batch.batch_id,
            )
            db.add(company)
            db.flush()
            note = "匯入新增"
        else:
            company.name = r["name"]
            company.website_url = r["website_url"]
            company.registered_products = r["registered_products"] or company.registered_products
            for old_cl in db.scalars(
                select(Classification).where(Classification.company_id == company.company_id, Classification.is_current)
            ):
                old_cl.is_current = False
            db.flush()
            note = f"匯入更新：{', '.join(r['changed_fields'])}"
        assert run is not None
        db.add(
            Classification(
                company_id=company.company_id,
                run_id=run.run_id,
                industry_id=r["industry_id"],
                customer_type=r["customer_type"],
                likelihood=r["likelihood"],
                is_competitor=r["is_competitor"],
                priority=r["priority"],
                score=r["score"],
                reason=r["reason"],
                is_current=True,
            )
        )
        db.add(
            ActivityLog(
                company_id=company.company_id,
                user_id=user.user_id if user else None,
                action="import",
                to_value=f"batch {batch.batch_id}",
                note=note,
            )
        )

    batch.run_id = run.run_id if run else None
    batch.rows_created = sum(r["action"] == "create" for r in rows)
    batch.rows_updated = sum(r["action"] == "update" for r in rows)
    batch.rows_unchanged = sum(r["action"] == "unchanged" for r in rows)
    batch.status = "committed"
    db.commit()
    return batch


def cancel_batch(db: Session, batch: ImportBatch) -> ImportBatch:
    if batch.status != "previewed":
        raise AppError("IMPORT_NOT_PREVIEWED", "這個匯入批次已經確認或取消過了", 409)
    batch.status = "cancelled"
    batch.payload = None
    db.commit()
    return batch
