"""KPI 與下拉選單用的維度資料（F-REC-5）。KPI 一律讀 view，不在這裡重算。"""

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.domain.company_rules import REJECT_REASONS, STATUS_LABELS
from app.models import AppUser, DimIndustry, DimPriority, v_kpi_summary

router = APIRouter()


class Kpis(BaseModel):
    pending_review: int
    total_companies: int
    five_star: int
    sent_7d: int
    sent_total: int
    replied_total: int
    reply_rate: Decimal | None


class Industry(BaseModel):
    industry_id: int
    name: str
    is_prospect: bool


class Priority(BaseModel):
    priority: str
    label: str
    definition: str
    suggested_action: str
    stars: int


class SalesUser(BaseModel):
    user_id: int
    display_name: str
    role: str


class Dimensions(BaseModel):
    industries: list[Industry]
    priorities: list[Priority]
    reject_reasons: list[str]
    statuses: list[str]
    users: list[SalesUser]


@router.get("/metrics/kpis", response_model=Kpis)
def kpis(_: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> Kpis:
    row = db.execute(select(v_kpi_summary)).mappings().one()
    return Kpis.model_validate(dict(row))


@router.get("/dimensions", response_model=Dimensions)
def dimensions(_: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> Dimensions:
    return Dimensions(
        industries=[
            Industry(industry_id=i.industry_id, name=i.name, is_prospect=i.is_prospect)
            for i in db.scalars(select(DimIndustry).order_by(DimIndustry.industry_id))
        ],
        priorities=[
            Priority(
                priority=p.priority,
                label=p.label,
                definition=p.definition,
                suggested_action=p.suggested_action,
                stars=p.stars,
            )
            for p in db.scalars(select(DimPriority).order_by(DimPriority.priority))
        ],
        reject_reasons=list(REJECT_REASONS),
        statuses=list(STATUS_LABELS),
        users=[
            SalesUser(user_id=u.user_id, display_name=u.display_name, role=u.role)
            for u in db.scalars(select(AppUser).where(AppUser.is_active).order_by(AppUser.display_name))
        ],
    )
