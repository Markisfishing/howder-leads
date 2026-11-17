"""待辦提醒與每日催辦（M3-10b、F-CASE-3、F-DASH-4）。

提醒條件只在 view v_case_reminder（migration 0007）；這裡只讀 view。
每日催辦是 worker 的 case_daily 工作：把寄出 14 天還停在「已寄出」的案件標成「無回應」，做完排下一次。
"""

from collections import defaultdict
from datetime import datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import case_rules
from app.domain.send_limits import TAIPEI
from app.models import AppUser, CaseUpdate, Company, Job, SalesCase, v_case_reminder
from app.services import company_service as company_svc
from app.services import jobs

R = v_case_reminder.c
REMINDER_LABELS = {
    "overdue_report": "逾期未回報",
    "follow_up_due": "該追蹤了",
    "no_response": "無回應，建議電話或拜訪",
}
DAILY_KIND = "case_daily"
DAILY_HOUR = 6  # 每天台灣時間 6 點跑，業務上班前提醒就準備好


def kinds_by_case(db: Session, case_ids: list[int]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = defaultdict(list)
    if case_ids:
        for case_id, kind in db.execute(select(R.case_id, R.kind).where(R.case_id.in_(case_ids)).order_by(R.kind)):
            out[case_id].append(kind)
    return out


def _scope(user: AppUser):  # type: ignore[no-untyped-def]
    q = select(R.case_id, R.kind)
    if not company_svc.is_manager(user):
        q = q.where(R.owner_id == user.user_id)
    return q


def case_ids_with_reminders(db: Session, user: AppUser, kinds: set[str] | None = None) -> set[int]:
    q = _scope(user)
    if kinds:
        q = q.where(R.kind.in_(kinds))
    return {r[0] for r in db.execute(q)}


def summary(db: Session, user: AppUser) -> dict[str, int]:
    """各種提醒的件數（同一件案件有兩種提醒會各算一次）＋新名單待審核（F-DASH-4）。"""
    sub = _scope(user).subquery()
    counts = {k: int(n) for k, n in db.execute(select(sub.c.kind, func.count()).group_by(sub.c.kind))}
    out = {k: counts.get(k, 0) for k in REMINDER_LABELS}
    out["pending_review"] = int(
        db.scalar(select(func.count()).select_from(Company).where(Company.status == "pending_review")) or 0
    )
    return out


# ---------- 每日催辦 ----------
def next_daily_run(now: datetime) -> datetime:
    local = now.astimezone(TAIPEI)
    run = datetime.combine(local.date(), time(DAILY_HOUR), TAIPEI)
    if run <= local:
        run += timedelta(days=1)
    return run


def mark_no_response(db: Session, now: datetime) -> int:
    """寄出 14 天還是「已寄出」的案件 → 無回應，時間軸記一筆系統紀錄。回傳標了幾件。"""
    last_sent = (
        select(CaseUpdate.case_id, func.max(CaseUpdate.created_at).label("at"))
        .where(CaseUpdate.result == "sent")
        .group_by(CaseUpdate.case_id)
        .subquery()
    )
    rows = db.execute(
        select(SalesCase, func.coalesce(last_sent.c.at, SalesCase.opened_at))
        .outerjoin(last_sent, last_sent.c.case_id == SalesCase.case_id)
        .where(SalesCase.status == "sent", SalesCase.closed_at.is_(None))
        .with_for_update(of=SalesCase, skip_locked=True)
    ).all()
    n = 0
    for case, sent_at in rows:
        if not case_rules.needs_no_response(case.status, sent_at, now):
            continue
        case.status = case_rules.next_status(case.status, "no_response")
        db.add(
            CaseUpdate(
                case_id=case.case_id,
                channel="system",
                contact_id=case.contact_id,
                result="no_response",
                note=f"寄出 {case_rules.NO_RESPONSE_DAYS} 天沒有回覆，建議電話或拜訪",
                created_at=now,
            )
        )
        n += 1
    db.commit()
    return n


def run_daily(db: Session, now: datetime) -> int:
    """worker 的 case_daily：標無回應，然後排明天的（同一筆交易，不會漏排）。"""
    n = mark_no_response(db, now)
    jobs.enqueue(db, DAILY_KIND, {}, run_after=next_daily_run(now))
    db.commit()
    return n


def ensure_daily_job(db: Session, now: datetime) -> None:
    """worker 啟動時呼叫：佇列裡沒有待跑的 case_daily 就排一筆（立刻跑一次）。"""
    exists = db.scalar(
        select(func.count()).select_from(Job).where(Job.kind == DAILY_KIND, Job.status.in_(("queued", "running")))
    )
    if not exists:
        jobs.enqueue(db, DAILY_KIND, {}, run_after=now)
        db.commit()
