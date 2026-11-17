"""推薦清單與公司（F-REC-1 ~ F-REC-6）。"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import Select, asc, desc, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.config import Settings, get_settings
from app.db import get_db
from app.domain.company_rules import DomainError
from app.models import ActivityLog, AppUser, Classification, Contact, DimPriority, Review, v_recommendation
from app.services import company_service as svc

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


class CompanyPage(BaseModel):
    items: list[CompanyRow]
    total: int
    page: int
    page_size: int


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


def _filtered(stmt: Select[Any], user: AppUser, f: ListFilters) -> Select[Any]:
    stars, status, industry_id, owner = f.stars, f.status, f.industry_id, f.owner
    has_website, competitor, q = f.has_website, f.competitor, f.q
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


@router.get("/companies", response_model=CompanyPage)
def list_companies(
    stars: list[int] = Query(default=[]),
    status: list[str] = Query(default=[]),
    industry_id: int | None = None,
    owner: str | None = Query(default=None, description="me / none / 使用者 id"),
    has_website: bool | None = None,
    competitor: bool | None = None,
    q: str | None = Query(default=None, max_length=100),
    sort: SortKey = "recommended",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> CompanyPage:
    filters = ListFilters(
        stars=stars,
        status=status,
        industry_id=industry_id,
        owner=owner,
        has_website=has_website,
        competitor=competitor,
        q=q,
    )
    total = db.scalar(_filtered(select(func.count()).select_from(v_recommendation), user, filters)) or 0
    order = {
        "recommended": [desc(V.stars), V.score.desc().nulls_last(), asc(V.name)],
        "name": [asc(V.name)],
        "updated": [desc(V.updated_at)],
    }[sort]
    stmt = _filtered(select(v_recommendation), user, filters).order_by(*order)
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).mappings()
    return CompanyPage(
        items=[CompanyRow.model_validate(dict(r)) for r in rows], total=total, page=page, page_size=page_size
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
        {"contact_id": c.contact_id, "name": c.name, "title": c.title, "email": c.email, "unsubscribed": c.unsubscribed}
        for c in db.scalars(select(Contact).where(Contact.company_id == company_id))
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
    )


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
