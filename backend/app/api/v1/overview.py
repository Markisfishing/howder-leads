"""總覽（M3-12b、F-DASH-1～4）：KPI、名單漏斗、各來源回覆率、待辦提醒。數字只從 view 來。"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.domain.company_rules import DomainError
from app.models import AppUser
from app.services import metrics_service as svc
from app.services import reminder_service

router = APIRouter()


class OverviewKpis(BaseModel):
    companies: int
    high_priority: int
    sent: int
    replied: int
    reply_rate: Decimal | None  # 寄出少於 10 件時為 null（樣本不足）
    won: int
    won_amount_twd: Decimal


class FunnelStage(BaseModel):
    key: str
    label: str
    count: int
    rate: Decimal | None  # 和前一段比的留存率；第一段為 null


class SourceRate(BaseModel):
    source: str
    sent: int
    replied: int
    reply_rate: Decimal | None
    insufficient: bool


class ReminderCount(BaseModel):
    kind: str
    label: str
    count: int


class Overview(BaseModel):
    scope_owner_id: int | None  # null = 全團隊
    kpis: OverviewKpis
    funnel: list[FunnelStage]
    mle_funnel: dict[str, int] | None
    by_source: list[SourceRate]
    reminders: list[ReminderCount]


@router.get("/metrics/overview", response_model=Overview)
def overview(
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    industry: int | None = None,
    product_type: str | None = Query(default=None, max_length=100),
    owner: int | None = None,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> Overview:
    if date_from and date_to and date_from > date_to:
        raise DomainError("INVALID_DATE_RANGE", "開始日期不能晚於結束日期", 422)
    f = svc.OverviewFilter(
        date_from=date_from,
        date_to=date_to,
        industry_id=industry,
        product_type=product_type,
        owner_id=svc.scoped_owner(user, owner),
    )
    data = svc.overview(db, user, f)
    labels = {**reminder_service.REMINDER_LABELS, "pending_review": "新名單待審核"}
    data["reminders"] = [ReminderCount(kind=k, label=labels[k], count=data["reminders"][k]) for k in labels]
    return Overview.model_validate(data)
