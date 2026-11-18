"""推薦清單與公司（F-REC-1 ~ F-REC-6）。"""

import csv
import io
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import Select, asc, desc, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.config import Settings, get_settings
from app.db import get_db
from app.domain.company_rules import STATUS_LABELS, DomainError
from app.domain.send_limits import TAIPEI
from app.models import ActivityLog, AppUser, Classification, Contact, DimPriority, Review, v_recommendation
from app.services import company_service as svc
from app.services import site_service

router = APIRouter()
V = v_recommendation.c


class CompanyRow(BaseModel):
    company_id: int
    tax_id: str
    name: str
    website_url: str | None
    website_verified: bool
    status: str
    owner_id: int | None
    owner_name: str | None
    owner_locked_until: datetime | None
    added_manually: bool
    priority: str | None
    stars: int
    score: Decimal | None
    likelihood: str | None
    is_competitor: bool
    industry_id: int | None
    industry: str | None
    customer_type: str | None
    reason: str | None
    updated_at: datetime
    # CSV 欄位規格 v1（M3-06c、F-REC-7）；fit_stars 沒給時 view 已經用優先級星等補上
    country: str
    url_status: str
    source: str | None
    fit_stars: Decimal | None
    product_type: str | None
    tags: list[str]


class CompanyPage(BaseModel):
    items: list[CompanyRow]
    total: int
    page: int
    page_size: int


class SiteSummaryOut(BaseModel):
    status: str  # ok / failed
    summary: str | None
    error_code: str | None
    source_url: str | None
    fetched_at: datetime


class CompanyDetail(CompanyRow):
    registered_products: str | None
    model_industry_id: int | None
    run_id: int | None
    priority_label: str | None
    priority_definition: str | None
    suggested_action: str | None
    contacts: list[dict[str, Any]]
    reviews: list[dict[str, Any]]
    activities: list[dict[str, Any]]
    site_summary: "SiteSummaryOut | None" = None  # M4-08e：官網摘要（AI 寫信的公司背景）


class CompanyPatch(BaseModel):
    website_url: str | None = Field(default=None, max_length=500)
    clear_website: bool = False
    industry_id: int | None = None
    note: str | None = Field(default=None, max_length=2000)


class CompanyCreate(BaseModel):
    tax_id: str = Field(min_length=8, max_length=8)
    name: str = Field(min_length=1, max_length=200)
    website_url: str | None = Field(default=None, max_length=500)
    industry_id: int | None = None
    note: str | None = Field(default=None, max_length=2000)


class AssignBody(BaseModel):
    user_id: int


SortKey = Literal["recommended", "name", "updated"]


@dataclass(frozen=True)
class ListFilters:
    stars: list[int]
    status: list[str]
    industry_id: int | None
    owner: str | None
    has_website: bool | None
    competitor: bool | None
    q: str | None
    # M3-06c：CSV v1 欄位的篩選
    country: tuple[str, ...] = ()
    source: tuple[str, ...] = ()
    url_status: tuple[str, ...] = ()
    product_type: str | None = None
    tag: tuple[str, ...] = ()
    min_stars: float | None = None


def has_filters(f: ListFilters) -> bool:
    """有沒有任何篩選條件（候選公司沒有條件時不用先查一次 view）。"""
    return any(
        (
            f.stars,
            f.status,
            f.industry_id is not None,
            f.owner,
            f.has_website is not None,
            f.competitor is not None,
            f.q and f.q.strip(),
            f.country,
            f.source,
            f.url_status,
            f.product_type,
            f.tag,
            f.min_stars is not None,
        )
    )


NO_SOURCE = "none"  # source=none 篩選「未標示來源」


def apply_filters(stmt: Select[Any], user: AppUser, f: ListFilters) -> Select[Any]:
    stars, status, industry_id, owner = f.stars, f.status, f.industry_id, f.owner
    has_website, competitor, q = f.has_website, f.competitor, f.q
    if f.country:
        stmt = stmt.where(V.country.in_(f.country))
    if f.source:
        named = [s for s in f.source if s != NO_SOURCE]
        conds = [V.source.in_(named)] if named else []
        if NO_SOURCE in f.source:
            conds.append(V.source.is_(None))
        stmt = stmt.where(or_(*conds))
    if f.url_status:
        stmt = stmt.where(V.url_status.in_(f.url_status))
    if f.product_type:
        stmt = stmt.where(V.product_type.ilike(f"%{f.product_type.strip()}%"))
    if f.tag:
        stmt = stmt.where(V.tags.overlap(list(f.tag)))  # 命中任一個標籤
    if f.min_stars is not None:
        stmt = stmt.where(V.fit_stars >= f.min_stars)
    if stars:
        stmt = stmt.where(V.stars.in_(stars))
    if status:
        stmt = stmt.where(V.status.in_(status))
    if industry_id is not None:
        stmt = stmt.where(V.industry_id == industry_id)
    if owner == "me":
        stmt = stmt.where(V.owner_id == user.user_id)
    elif owner == "none":
        stmt = stmt.where(V.owner_id.is_(None))
    elif owner and owner.isdigit():
        stmt = stmt.where(V.owner_id == int(owner))
    if has_website is not None:
        stmt = stmt.where(V.website_url.is_not(None) if has_website else V.website_url.is_(None))
    if competitor is not None:
        stmt = stmt.where(V.is_competitor.is_(competitor))
    if q:
        term = q.strip()
        stmt = stmt.where(or_(V.name.ilike(f"%{term}%"), V.tax_id.startswith(term)))
    return stmt


def list_filters(
    stars: list[int] = Query(default=[]),
    status: list[str] = Query(default=[]),
    industry_id: int | None = None,
    owner: str | None = Query(default=None, description="me / none / 使用者 id"),
    has_website: bool | None = None,
    competitor: bool | None = None,
    q: str | None = Query(default=None, max_length=100),
    country: list[str] = Query(default=[]),
    source: list[str] = Query(default=[]),
    url_status: list[str] = Query(default=[]),
    product_type: str | None = Query(default=None, max_length=100),
    tag: list[str] = Query(default=[]),
    min_stars: float | None = Query(default=None, ge=0, le=5),
) -> ListFilters:
    """推薦清單與匯出共用的篩選參數（F-REC-2、F-REC-7、F-REC-8）。"""
    return ListFilters(
        stars=stars,
        status=status,
        industry_id=industry_id,
        owner=owner,
        has_website=has_website,
        competitor=competitor,
        q=q,
        country=tuple(c.upper() for c in country),
        source=tuple(source),
        url_status=tuple(url_status),
        product_type=product_type,
        tag=tuple(tag),
        min_stars=min_stars,
    )


ORDER = {
    # F-REC-1：先依適合度星等（小數），再依分數
    "recommended": [V.fit_stars.desc().nulls_last(), desc(V.stars), V.score.desc().nulls_last(), asc(V.name)],
    "name": [asc(V.name)],
    "updated": [desc(V.updated_at)],
}


@router.get("/companies", response_model=CompanyPage)
def list_companies(
    filters: ListFilters = Depends(list_filters),
    sort: SortKey = "recommended",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> CompanyPage:
    total = db.scalar(apply_filters(select(func.count()).select_from(v_recommendation), user, filters)) or 0
    stmt = apply_filters(select(v_recommendation), user, filters).order_by(*ORDER[sort])
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).mappings()
    return CompanyPage(
        items=[CompanyRow.model_validate(dict(r)) for r in rows], total=total, page=page, page_size=page_size
    )


# ---------- 匯出（M3-13a、F-REC-8）----------
def _text(key: str) -> Callable[[Mapping[str, Any]], str]:
    return lambda r: "" if r[key] is None else str(r[key])


# 欄位 key → （表頭、取值）。前端「欄位自選」用同一組 key；不放聯絡人 email（個資只在系統裡看）
EXPORT_COLUMNS: dict[str, tuple[str, Callable[[Mapping[str, Any]], str]]] = {
    "tax_id": ("統編", _text("tax_id")),
    "name": ("公司名稱", _text("name")),
    "fit_stars": ("適合度星等", _text("fit_stars")),
    "priority": ("開發優先級", _text("priority")),
    "industry": ("產業", _text("industry")),
    "product_type": ("產品類型", _text("product_type")),
    "tags": ("命中標籤", lambda r: "、".join(r["tags"] or [])),
    "likelihood": ("使用可能性", _text("likelihood")),
    "reason": ("推薦理由", _text("reason")),
    "status": ("狀態", lambda r: STATUS_LABELS.get(r["status"], r["status"])),
    "owner_name": ("負責業務", _text("owner_name")),
    "website_url": ("官網", _text("website_url")),
    "url_status": ("網址狀態", _text("url_status")),
    "country": ("國別", _text("country")),
    "source": ("資料來源", _text("source")),
    "customer_type": ("客戶屬性", _text("customer_type")),
    "score": ("分數", _text("score")),
    "updated_at": ("最後更新", lambda r: r["updated_at"].astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M")),
}
DEFAULT_EXPORT = ["tax_id", "name", "fit_stars", "priority", "industry", "reason", "status", "owner_name"]
EXPORT_LIMIT = 20000


def export_csv(rows: Sequence[Mapping[str, Any]], columns: list[str]) -> str:
    buf = io.StringIO()
    buf.write("\ufeff")  # UTF-8 BOM：Excel 直接開不會亂碼
    w = csv.writer(buf)
    w.writerow([EXPORT_COLUMNS[c][0] for c in columns])
    for r in rows:
        w.writerow([EXPORT_COLUMNS[c][1](r) for c in columns])
    return buf.getvalue()


@router.get("/companies/export", response_class=Response)
def export_companies(
    filters: ListFilters = Depends(list_filters),
    sort: SortKey = "recommended",
    columns: list[str] = Query(default=[], max_length=len(EXPORT_COLUMNS)),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    """依目前篩選匯出 CSV；columns 是畫面上選的欄位（沒給就用預設欄位），順序照傳入的。"""
    unknown = [c for c in columns if c not in EXPORT_COLUMNS]
    if unknown:
        raise DomainError("INVALID_EXPORT_COLUMN", f"不能匯出的欄位：{'、'.join(unknown)}", 422)
    cols = list(dict.fromkeys(columns)) or DEFAULT_EXPORT
    stmt = apply_filters(select(v_recommendation), user, filters).order_by(*ORDER[sort]).limit(EXPORT_LIMIT)
    rows = [dict(r) for r in db.execute(stmt).mappings()]
    return Response(
        content=export_csv(rows, cols).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="companies.csv"'},
    )


def _detail(db: Session, company_id: int) -> CompanyDetail:
    row = db.execute(select(v_recommendation).where(V.company_id == company_id)).mappings().first()
    if row is None:
        raise DomainError("COMPANY_NOT_FOUND", "找不到這家公司", 404)
    company = svc.get_company(db, company_id)
    cl = db.scalar(select(Classification).where(Classification.company_id == company_id, Classification.is_current))
    pr = db.get(DimPriority, cl.priority) if cl and cl.priority else None
    names = dict(db.execute(select(AppUser.user_id, AppUser.display_name)).all())
    contacts = [
        {
            "contact_id": c.contact_id,
            "name": c.name,
            "title": c.title,
            "email": c.email,
            "source": c.source,
            "is_verified": c.is_verified,
            "unsubscribed": c.unsubscribed,
        }
        for c in db.scalars(select(Contact).where(Contact.company_id == company_id).order_by(Contact.contact_id))
    ]
    reviews = [
        {
            "decision": r.decision,
            "reject_reason": r.reject_reason,
            "note": r.note,
            "reviewer": names.get(r.reviewer_id),
            "created_at": r.created_at,
        }
        for r in db.scalars(select(Review).where(Review.company_id == company_id).order_by(Review.created_at.desc()))
    ]
    activities = [
        {
            "action": a.action,
            "from_value": a.from_value,
            "to_value": a.to_value,
            "note": a.note,
            "user": names.get(a.user_id) if a.user_id else None,
            "created_at": a.created_at,
        }
        for a in db.scalars(
            select(ActivityLog)
            .where(ActivityLog.company_id == company_id)
            .order_by(ActivityLog.created_at.desc(), ActivityLog.log_id.desc())
            .limit(50)
        )
    ]
    return CompanyDetail(
        **dict(row),
        registered_products=company.registered_products,
        model_industry_id=cl.industry_id if cl else None,
        priority_label=pr.label if pr else None,
        priority_definition=pr.definition if pr else None,
        suggested_action=pr.suggested_action if pr else None,
        contacts=contacts,
        reviews=reviews,
        activities=activities,
        site_summary=_site_summary(db, company_id),
    )


def _site_summary(db: Session, company_id: int) -> "SiteSummaryOut | None":
    row = site_service.get_summary(db, company_id)
    if row is None:
        return None
    return SiteSummaryOut(
        status=row.status,
        summary=row.summary,
        error_code=row.error_code,
        source_url=row.source_url,
        fetched_at=row.fetched_at,
    )


@router.post("/companies/{company_id}/site-summary/refresh", response_model=CompanyDetail, status_code=202)
def refresh_site_summary(
    company_id: int, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
) -> CompanyDetail:
    """M4-08e：業務按「重新抓取」。要有官網；被其他業務鎖定的公司只有主管能操作。"""
    company = svc.get_company(db, company_id)
    svc.ensure_can_act(company, user)
    if not company.website_url:
        raise DomainError("SITE_NO_URL", "這家公司沒有官網，沒辦法抓取", 422)
    site_service.invalidate(db, company_id)
    db.flush()
    site_service.enqueue(db, company_id, user.user_id)
    db.commit()
    return _detail(db, company_id)


@router.get("/companies/{company_id}", response_model=CompanyDetail)
def get_company(company_id: int, _: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> CompanyDetail:
    return _detail(db, company_id)


@router.patch("/companies/{company_id}", response_model=CompanyDetail)
def patch_company(
    company_id: int, body: CompanyPatch, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
) -> CompanyDetail:
    company = svc.get_company(db, company_id)
    svc.update_company(
        db,
        company,
        user,
        website_url=body.website_url.strip() if body.website_url else None,
        clear_website=body.clear_website,
        industry_id=body.industry_id,
        note=body.note,
    )
    return _detail(db, company_id)


@router.post("/companies", response_model=CompanyDetail, status_code=201)
def create_company(
    body: CompanyCreate, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
) -> CompanyDetail:
    company = svc.create_manual(
        db,
        user,
        tax_id=body.tax_id,
        name=body.name,
        website_url=body.website_url,
        industry_id=body.industry_id,
        note=body.note,
    )
    return _detail(db, company.company_id)


@router.post("/companies/{company_id}/claim", response_model=CompanyDetail)
def claim_company(
    company_id: int,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CompanyDetail:
    svc.claim(db, svc.get_company(db, company_id), user, settings.lock_days)
    return _detail(db, company_id)


@router.post("/companies/{company_id}/release", response_model=CompanyDetail)
def release_company(
    company_id: int, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
) -> CompanyDetail:
    svc.release(db, svc.get_company(db, company_id), user)
    return _detail(db, company_id)


@router.post("/companies/{company_id}/assign", response_model=CompanyDetail)
def assign_company(
    company_id: int,
    body: AssignBody,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CompanyDetail:
    svc.assign(db, svc.get_company(db, company_id), body.user_id, user, settings.lock_days)
    return _detail(db, company_id)
