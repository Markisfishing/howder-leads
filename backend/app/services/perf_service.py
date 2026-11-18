"""績效（M4-01b、F-TRK-5）與名單品質（M4-02a、F-MLE-1）。

一律讀 v_case_perf／v_reject_reasons：寄出、回覆、成交的定義在 view（CLAUDE.md 第 4 節第 4 點），
這裡只依條件加總，不重新定義；比例在後端算好給前端，前端不重算。
樣本不足（寄出少於 10 件）的列不算比例，排在後面。
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import ModelRun, v_case_perf, v_reject_reasons
from app.services.metrics_service import NO_SOURCE_LABEL, OverviewFilter, _bounds, _count_if, min_sample, rate

P = v_case_perf.c

STAR_LABELS = {5: "★★★★★ 第一優先", 4: "★★★★ 可開發", 2: "★★ 觀察／策略", 1: "★ 暫不優先", 0: "未評分（手動加入）"}
BREAKDOWNS = ("stars", "source", "tag")


@dataclass(frozen=True)
class PerfFilter:
    date_from: date | None = None
    date_to: date | None = None
    owner_id: int | None = None  # None = 全團隊（只有主管）


def _perf(stmt: Select[Any], f: PerfFilter) -> Select[Any]:
    stmt = stmt.where(P.is_sent)
    if f.owner_id is not None:
        stmt = stmt.where(P.owner_id == f.owner_id)
    start, end = _bounds(OverviewFilter(date_from=f.date_from, date_to=f.date_to))
    if start:
        stmt = stmt.where(P.sent_at >= start)
    if end:
        stmt = stmt.where(P.sent_at < end)
    return stmt


def _row(ms: int, key: str, label: str, sent: int, replied: int, won: int, amount: Any) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "sent": sent,
        "replied": replied,
        "reply_rate": rate(replied, sent, ms),
        "won": won,
        "win_rate": rate(won, sent, ms),
        "won_amount_twd": Decimal(amount or 0),
        "insufficient": sent < ms,
    }


def _order(x: dict[str, Any]) -> tuple[bool, Decimal, int, str]:
    # 樣本夠的在前，依成交率、再依寄出件數；樣本不足的排在後面
    return (bool(x["insufficient"]), -(x["win_rate"] or Decimal(0)), -int(x["sent"]), str(x["label"]))


def win_rate(db: Session, f: PerfFilter, by: str) -> list[dict[str, Any]]:
    """各星級／各資料來源／各產品標籤的回覆率與成交率。一家公司有多個標籤時，每個標籤各算一次。"""
    if by not in BREAKDOWNS:
        raise ValueError(by)
    if by == "tag":
        return _by_tag(db, f)
    col = func.coalesce(P.stars, 0) if by == "stars" else func.coalesce(P.source, NO_SOURCE_LABEL)
    rows = db.execute(
        _perf(
            select(
                col,
                func.count(),
                _count_if(P.is_replied),
                _count_if(P.is_won),
                func.coalesce(func.sum(P.won_amount), 0),
            ).select_from(v_case_perf),
            f,
        ).group_by(col)
    ).all()
    items = []
    for key, sent, replied, won, amount in rows:
        label = STAR_LABELS.get(int(key), f"{key} 星") if by == "stars" else str(key)
        items.append(_row(min_sample(db), str(key), label, int(sent), int(replied), int(won), amount))
    items.sort(key=_order)
    return items


def _by_tag(db: Session, f: PerfFilter) -> list[dict[str, Any]]:
    rows = db.execute(_perf(select(P.tags, P.is_replied, P.is_won, P.won_amount).select_from(v_case_perf), f)).all()
    acc: dict[str, list[Any]] = {}
    for tags, replied, won, amount in rows:
        for tag in tags or ["（無標籤）"]:
            a = acc.setdefault(tag, [0, 0, 0, Decimal(0)])
            a[0] += 1
            a[1] += 1 if replied else 0
            a[2] += 1 if won else 0
            a[3] += Decimal(amount or 0)
    items = [_row(min_sample(db), tag, tag, a[0], a[1], a[2], a[3]) for tag, a in acc.items()]
    items.sort(key=_order)
    return items


def by_template(db: Session, f: PerfFilter) -> list[dict[str, Any]]:
    """各模板（含版本）的回覆率與成交率；沒有模板的案件（例如直接加入追蹤）不在這裡。"""
    rows = db.execute(
        _perf(
            select(
                P.template_family_id,
                P.template_name,
                P.template_version,
                func.count(),
                _count_if(P.is_replied),
                _count_if(P.is_won),
                func.coalesce(func.sum(P.won_amount), 0),
            )
            .select_from(v_case_perf)
            .where(P.template_family_id.is_not(None))
            .group_by(P.template_family_id, P.template_name, P.template_version),
            f,
        )
    ).all()
    items = [
        _row(min_sample(db), f"{fam}:{ver}", f"{name}（第 {ver} 版）", int(s), int(r), int(w), amt)
        for fam, name, ver, s, r, w, amt in rows
    ]
    items.sort(key=_order)
    return items


def by_rep(db: Session, f: PerfFilter) -> list[dict[str, Any]]:
    """業務排行：依成交金額、成交件數排。業務只看得到自己（呼叫端用 scoped_owner）。"""
    rows = db.execute(
        _perf(
            select(
                P.owner_id,
                P.owner_name,
                func.count(),
                _count_if(P.is_replied),
                _count_if(P.is_won),
                func.coalesce(func.sum(P.won_amount), 0),
            )
            .select_from(v_case_perf)
            .group_by(P.owner_id, P.owner_name),
            f,
        )
    ).all()
    items = [_row(min_sample(db), str(oid), str(name), int(s), int(r), int(w), amt) for oid, name, s, r, w, amt in rows]
    items.sort(key=lambda x: (-x["won_amount_twd"], -x["won"], -x["sent"], x["label"]))
    return items


def reject_reasons(db: Session, run_id: int | None) -> dict[str, Any]:
    """各批次（model run）的排除原因分布；沒指定批次就用最新一批。share 由 view 算好。"""
    runs = db.execute(
        select(ModelRun.run_id, ModelRun.model_name, ModelRun.created_at).order_by(ModelRun.run_id.desc())
    ).all()
    chosen = run_id if run_id is not None else (runs[0].run_id if runs else None)
    rows = (
        db.execute(
            select(v_reject_reasons.c.reject_reason, v_reject_reasons.c.n, v_reject_reasons.c.share)
            .where(v_reject_reasons.c.run_id == chosen)
            .order_by(v_reject_reasons.c.n.desc(), v_reject_reasons.c.reject_reason)
        ).all()
        if chosen is not None
        else []
    )
    return {
        "run_id": chosen,
        "runs": [{"run_id": r.run_id, "model_name": r.model_name, "created_at": r.created_at} for r in runs],
        "total": sum(int(r.n) for r in rows),
        "items": [{"reason": r.reject_reason, "count": int(r.n), "share": r.share} for r in rows],
    }
