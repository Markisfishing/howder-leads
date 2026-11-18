"""績效與名單品質（M4-01b、M4-02a；F-TRK-5、F-MLE-1）。數字只從 view 來，前端不重算。"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.domain.company_rules import DomainError
from app.models import AppUser
from app.services import company_service as company_svc
from app.services import metrics_service, perf_service

router = APIRouter()


class PerfRow(BaseModel):
    key: str
    label: str
    sent: int
    replied: int
    reply_rate: Decimal | None  # 寄出少於 10 件為 null
    won: int
    win_rate: Decimal | None
    won_amount_twd: Decimal
    insufficient: bool


class PerfTable(BaseModel):
    scope_owner_id: int | None  # null = 全團隊
    items: list[PerfRow]


def _filter(user: AppUser, date_from: date | None, date_to: date | None, owner: int | None) -> perf_service.PerfFilter:
    if date_from and date_to and date_from > date_to:
        raise DomainError("INVALID_DATE_RANGE", "開始日期不能晚於結束日期", 422)
    return perf_service.PerfFilter(
        date_from=date_from, date_to=date_to, owner_id=metrics_service.scoped_owner(user, owner)
    )


@router.get("/metrics/win-rate", response_model=PerfTable)
def win_rate(
    by: Literal["stars", "source", "tag"] = "stars",
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    owner: int | None = None,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> PerfTable:
    f = _filter(user, date_from, date_to, owner)
    return PerfTable(scope_owner_id=f.owner_id, items=[PerfRow(**r) for r in perf_service.win_rate(db, f, by)])


@router.get("/metrics/templates", response_model=PerfTable)
def templates(
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    owner: int | None = None,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> PerfTable:
    f = _filter(user, date_from, date_to, owner)
    return PerfTable(scope_owner_id=f.owner_id, items=[PerfRow(**r) for r in perf_service.by_template(db, f)])


@router.get("/metrics/reps", response_model=PerfTable)
def reps(
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    owner: int | None = None,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> PerfTable:
    """業務排行：業務只看得到自己那一列；主管看全團隊。"""
    f = _filter(user, date_from, date_to, owner)
    return PerfTable(scope_owner_id=f.owner_id, items=[PerfRow(**r) for r in perf_service.by_rep(db, f)])


class RejectItem(BaseModel):
    reason: str | None
    count: int
    share: Decimal | None


class ModelRunOut(BaseModel):
    run_id: int
    model_name: str
    created_at: datetime


class RejectReport(BaseModel):
    run_id: int | None
    runs: list[ModelRunOut]
    total: int
    items: list[RejectItem]


@router.get("/metrics/reject-reasons", response_model=RejectReport)
def reject_reasons(
    run_id: int | None = None, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
) -> RejectReport:
    if not company_svc.is_manager(user):
        raise DomainError("FORBIDDEN", "只有主管或管理員可以看名單品質報表", 403)
    return RejectReport.model_validate(perf_service.reject_reasons(db, run_id))
