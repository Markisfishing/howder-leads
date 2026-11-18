"""總覽頁數字（M3-12b、F-DASH-1～4）。

「寄出」「回覆」「成交」的定義只在 view v_case_fact／v_company_fact（migration 0010）；
這裡只依篩選條件加總 view 的旗標，比例在後端算好給前端，前端不重算（CLAUDE.md 第 4 節第 4 點）。

範圍：
- 名單、高優先、審核通過：整個共用名單池（只套產業、產品類型篩選）
- 寄出、回覆、成交：依案件負責業務；業務只看自己的，主管可以選業務或看全團隊
- 日期區間套在「寄出日」（台灣日期）
"""

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.domain.send_limits import TAIPEI
from app.models import AppUser, ImportBatch, v_case_fact, v_company_fact
from app.services import company_service as company_svc
from app.services import reminder_service

F = v_case_fact.c
C = v_company_fact.c
MIN_SAMPLE = 10  # 和 v_kpi_summary 一樣：寄出少於 10 件不算比例，標「樣本不足」
NO_SOURCE_LABEL = "未標示"


@dataclass(frozen=True)
class OverviewFilter:
    date_from: date | None = None
    date_to: date | None = None
    industry_id: int | None = None
    product_type: str | None = None
    owner_id: int | None = None  # None = 全團隊（只有主管）


def scoped_owner(user: AppUser, requested: int | None) -> int | None:
    """業務只能看自己的；主管可以指定業務或看全團隊。"""
    return requested if company_svc.is_manager(user) else user.user_id


def rate(n: int, d: int, min_sample: int = MIN_SAMPLE) -> Decimal | None:
    if d < min_sample or d == 0:
        return None
    return (Decimal(n) / Decimal(d)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _bounds(f: OverviewFilter) -> tuple[datetime | None, datetime | None]:
    start = datetime.combine(f.date_from, time(0), TAIPEI) if f.date_from else None
    end = datetime.combine(f.date_to + timedelta(days=1), time(0), TAIPEI) if f.date_to else None
    return start, end


def _pool(stmt: Select[Any], f: OverviewFilter, cols: Any) -> Select[Any]:
    if f.industry_id is not None:
        stmt = stmt.where(cols.industry_id == f.industry_id)
    if f.product_type:
        stmt = stmt.where(cols.product_type.ilike(f"%{f.product_type.strip()}%"))
    return stmt


def _cases(stmt: Select[Any], f: OverviewFilter) -> Select[Any]:
    stmt = _pool(stmt, f, F)
    if f.owner_id is not None:
        stmt = stmt.where(F.owner_id == f.owner_id)
    start, end = _bounds(f)
    if start:
        stmt = stmt.where(F.sent_at >= start)
    if end:
        stmt = stmt.where(F.sent_at < end)
    return stmt


def _count_if(cond: Any) -> Any:
    return func.count().filter(cond)


def kpis(db: Session, f: OverviewFilter) -> dict[str, Any]:
    pool = db.execute(_pool(select(func.count(), _count_if(C.stars == 5)).select_from(v_company_fact), f, C)).one()
    cases = db.execute(
        _cases(
            select(
                _count_if(F.is_sent),
                _count_if(F.is_sent & F.is_replied),
                _count_if(F.is_won),
                func.coalesce(func.sum(F.won_amount), 0),
            ).select_from(v_case_fact),
            f,
        )
    ).one()
    sent, replied, won, amount = int(cases[0]), int(cases[1]), int(cases[2]), Decimal(cases[3])
    return {
        "companies": int(pool[0]),
        "high_priority": int(pool[1]),
        "sent": sent,
        "replied": replied,
        "reply_rate": rate(replied, sent),
        "won": won,
        "won_amount_twd": amount,
    }


def funnel(db: Session, f: OverviewFilter) -> list[dict[str, Any]]:
    """名單 → 審核通過 → 已寄信 → 回覆 → 成交；每段附上和前一段比的留存率（F-DASH-2）。"""
    total, approved = db.execute(
        _pool(select(func.count(), _count_if(C.is_approved)).select_from(v_company_fact), f, C)
    ).one()
    # 後三段依「案件」的負責業務與寄出日算（寄信不會自動認領公司，不能用 company.owner_id）；一家公司只算一次
    distinct: Any = func.count(F.company_id.distinct())
    contacted = select(
        distinct.filter(F.is_sent),
        distinct.filter(F.is_sent & F.is_replied),
        distinct.filter(F.is_sent & F.is_won),
    ).select_from(v_case_fact)
    sent, replied, won = db.execute(_cases(contacted, f)).one()
    stages = [("list", "名單", total), ("approved", "審核通過", approved), ("sent", "已寄信", sent)]
    stages += [("replied", "回覆", replied), ("won", "成交", won)]
    out: list[dict[str, Any]] = []
    prev: int | None = None
    for key, label, n in stages:
        out.append({"key": key, "label": label, "count": int(n), "rate": rate(int(n), prev, 1) if prev else None})
        prev = int(n)
    return out


def by_source(db: Session, f: OverviewFilter) -> list[dict[str, Any]]:
    """各來源回覆率，依回覆率高到低；寄出不到 10 件的標「樣本不足」排在後面（F-DASH-3）。"""
    label = func.coalesce(F.source, NO_SOURCE_LABEL)
    rows = db.execute(
        _cases(
            select(label, _count_if(F.is_sent), _count_if(F.is_sent & F.is_replied))
            .select_from(v_case_fact)
            .where(F.is_sent)
            .group_by(label),
            f,
        )
    ).all()
    items: list[dict[str, Any]] = [
        {
            "source": str(src),
            "sent": int(s),
            "replied": int(r),
            "reply_rate": rate(int(r), int(s)),
            "insufficient": int(s) < MIN_SAMPLE,
        }
        for src, s, r in rows
    ]
    items.sort(key=_source_order)
    return items


def mle_funnel(db: Session) -> dict[str, int] | None:
    """最近一次確認匯入、而且有附漏斗數字的批次（MLE 提供，只顯示）。"""
    batches = db.scalars(
        select(ImportBatch)
        .where(ImportBatch.status == "committed", ImportBatch.funnel.is_not(None))
        .order_by(ImportBatch.batch_id.desc())
    )
    # PostgreSQL JSONB 的 JSON null 不是 SQL NULL，is_not(None) 仍可能撈到它。
    for batch in batches:
        if isinstance(batch.funnel, dict) and batch.funnel:
            return dict(batch.funnel)
    return None


def overview(db: Session, user: AppUser, f: OverviewFilter) -> dict[str, Any]:
    current = kpis(db, f)
    comparison = None
    if f.date_from and f.date_to:
        days = (f.date_to - f.date_from).days + 1
        previous_to = f.date_from - timedelta(days=1)
        previous = kpis(db, replace(f, date_from=previous_to - timedelta(days=days - 1), date_to=previous_to))
        current_rate = current["reply_rate"]
        previous_rate = previous["reply_rate"]
        comparison = {
            "sent_delta": current["sent"] - previous["sent"],
            "reply_rate_delta": (
                current_rate - previous_rate if current_rate is not None and previous_rate is not None else None
            ),
            "won_delta": current["won"] - previous["won"],
            "won_amount_delta_twd": current["won_amount_twd"] - previous["won_amount_twd"],
            "reply_rate_target": Decimal("0.05"),
        }
    return {
        "scope_owner_id": f.owner_id,
        "kpis": current,
        "comparison": comparison,
        "funnel": funnel(db, f),
        "mle_funnel": mle_funnel(db),
        "by_source": by_source(db, f),
        "reminders": reminder_service.summary(db, user),
    }


def _source_order(x: dict[str, Any]) -> tuple[bool, Decimal, int, str]:
    return (bool(x["insufficient"]), -(x["reply_rate"] or Decimal(0)), -int(x["sent"]), str(x["source"]))
