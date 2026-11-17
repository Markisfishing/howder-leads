"""案件：寄出時開案、加入追蹤、人工回填、列表與時間軸（M3-09、F-CASE-1、F-CASE-2、F-CASE-4、F-REC-9）。

系統不讀業務信箱（ADR 0004），回覆與結果都靠業務回填。回填會帶動公司狀態（SPEC 3.1）。
"""

import csv
import io
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.domain import case_rules, company_rules
from app.domain.company_rules import DomainError, Ownership
from app.domain.send_limits import TAIPEI
from app.models import AppUser, CaseUpdate, Company, Contact, EmailMessage, SalesCase
from app.services import company_service as company_svc

TRACKABLE = frozenset({"approved"})  # 加入追蹤只限「已通過」還沒寄信的公司
MAX_TRACK = 200


def taipei_today(now: datetime) -> date:
    return now.astimezone(TAIPEI).date()


def open_case(db: Session, company_id: int, *, lock: bool = False) -> SalesCase | None:
    q = select(SalesCase).where(SalesCase.company_id == company_id, SalesCase.closed_at.is_(None))
    if lock:
        q = q.with_for_update()
    return db.scalar(q)


def _system_update(db: Session, case: SalesCase, user: AppUser | None, result: str, note: str, now: datetime) -> None:
    db.add(
        CaseUpdate(
            case_id=case.case_id,
            user_id=user.user_id if user else None,
            channel="system",
            contact_id=case.contact_id,
            result=result,
            note=note,
            created_at=now,
        )
    )


# ---------- 開案（F-CASE-1、F-REC-9）----------
def open_for_email(
    db: Session, company: Company, contact_id: int, sender: AppUser, message: EmailMessage, now: datetime
) -> SalesCase:
    """worker 寄出成功時呼叫（不 commit，和寄出紀錄一起 commit）。

    已經有未結案的案件（例如先加入追蹤、或無回應後再寄一封）就加在同一件的時間軸，不另開。
    """
    case = open_case(db, company.company_id, lock=True)
    if case is None:
        case = SalesCase(
            company_id=company.company_id,
            contact_id=contact_id,
            owner_id=sender.user_id,
            origin="email",
            message_id=message.message_id,
            status="sent",
            opened_at=now,
        )
        db.add(case)
        db.flush()
    else:
        if "sent" in case_rules.CASE_TRANSITIONS[case.status]:
            case.status = "sent"  # 追蹤中、無回應 → 已寄出，重新開始算 7／14 天
        case.message_id = case.message_id or message.message_id
        case.contact_id = case.contact_id or contact_id
    _system_update(db, case, sender, "sent", f"寄出開發信（草稿 #{message.draft_id}）", now)
    company_svc.log(db, company, sender, "case_open", to_value=f"case:{case.case_id}")
    return case


def add_tracking(db: Session, user: AppUser, company_ids: list[int], now: datetime, lock_days: int) -> list[SalesCase]:
    """批次「加入追蹤」：不寄信直接開案（例如先打電話、拜訪）。整批檢查，任何一家不行就整批不動。"""
    ids = sorted(set(company_ids))
    if not ids:
        raise DomainError("NO_TARGETS", "請至少選一家公司", 422)
    if len(ids) > MAX_TRACK:
        raise DomainError("TOO_MANY_TARGETS", f"一次最多 {MAX_TRACK} 家", 422)
    companies = list(
        db.scalars(select(Company).where(Company.company_id.in_(ids)).order_by(Company.company_id).with_for_update())
    )
    if len(companies) != len(ids):
        raise DomainError("COMPANY_NOT_FOUND", "有公司不存在，請重新整理", 404)
    problems: list[str] = []
    for c in companies:
        try:
            company_rules.ensure_can_act(
                Ownership(c.owner_id, c.owner_locked_until), user.user_id, now, company_svc.is_manager(user)
            )
            if c.status not in TRACKABLE:
                raise DomainError("NOT_TRACKABLE", "只有「已通過」還沒寄信的公司可以加入追蹤")
            if open_case(db, c.company_id) is not None:
                raise DomainError("CASE_EXISTS", "已經有進行中的案件")
        except DomainError as e:
            problems.append(f"{c.name}：{e.message}")
    if problems:
        db.rollback()
        raise DomainError("TRACK_REJECTED", "；".join(problems[:5]), 409)

    contacts: dict[int, int] = {}
    for ct in db.scalars(select(Contact).where(Contact.company_id.in_(ids)).order_by(Contact.contact_id)):
        if not ct.unsubscribed:
            contacts.setdefault(ct.company_id, ct.contact_id)
    cases = []
    for c in companies:
        # 開始追蹤就是在經營這家公司：沒人負責時順便認領（鎖定期間其他業務不能寄信）
        if c.owner_id is None:
            owner = company_rules.claim(Ownership(None, None), user.user_id, now, lock_days)
            c.owner_id, c.owner_locked_until = owner.owner_id, owner.locked_until
            company_svc.log(db, c, user, "claim", None, str(user.user_id), "加入追蹤時認領")
        case = SalesCase(
            company_id=c.company_id,
            contact_id=contacts.get(c.company_id),
            owner_id=user.user_id,
            origin="tracking",
            status="tracking",
            opened_at=now,
        )
        db.add(case)
        db.flush()
        company_svc.log(db, c, user, "case_open", to_value=f"case:{case.case_id}", note="加入追蹤")
        cases.append(case)
    db.commit()
    return cases


# ---------- 權限 ----------
def can_view(user: AppUser, case: SalesCase) -> bool:
    return company_svc.is_manager(user) or case.owner_id == user.user_id


def get_case(db: Session, user: AppUser, case_id: int, *, lock: bool = False) -> SalesCase:
    q = select(SalesCase).where(SalesCase.case_id == case_id)
    if lock:
        q = q.with_for_update()
    case = db.scalar(q)
    if case is None or not can_view(user, case):  # 別人的案件一律當作不存在
        raise DomainError("CASE_NOT_FOUND", "找不到這件案件", 404)
    return case


# ---------- 回填（F-CASE-2）----------
def add_update(
    db: Session,
    user: AppUser,
    case_id: int,
    data: case_rules.UpdateInput,
    contact_id: int | None,
    now: datetime,
) -> SalesCase:
    case = get_case(db, user, case_id, lock=True)
    clean = case_rules.validate_update(data, taipei_today(now))
    new_status = case_rules.next_status(case.status, clean.result)
    company = company_svc.get_company(db, case.company_id)
    if contact_id is not None:
        contact = db.get(Contact, contact_id)
        if contact is None or contact.company_id != case.company_id:
            raise DomainError("CONTACT_NOT_IN_COMPANY", "聯絡人不屬於這家公司", 422)
    # 狀態和結案時間要一起改（資料庫 CHECK：won／lost ⇔ closed_at 有值）
    case.status = new_status
    case.closed_at = now if new_status in case_rules.CLOSED else None

    db.add(
        CaseUpdate(
            case_id=case.case_id,
            user_id=user.user_id,
            channel=clean.channel,
            contact_id=contact_id or case.contact_id,
            result=clean.result,
            note=clean.note,
            next_follow_up=clean.next_follow_up,
            amount_twd=clean.amount_twd,
            created_at=now,
        )
    )
    case.last_update_at = now
    case.next_follow_up = clean.next_follow_up
    if clean.result in case_rules.CLOSED:
        case.next_follow_up = None
    if clean.result == "won":
        case.amount_twd = clean.amount_twd

    target = case_rules.company_target(clean.result)
    label = case_rules.RESULT_LABELS[clean.result]
    for step in case_rules.company_path(company.status, target) if target else []:
        company_svc.change_status(db, company, step, user, f"案件 {case.case_no} 回填：{label}")
    company_svc.log(db, company, user, "case_update", to_value=f"case:{case.case_id}:{clean.result}")
    db.commit()
    return case


def close_for_unsubscribe(db: Session, user: AppUser, case: SalesCase, now: datetime) -> None:
    """客戶要求退訂（F-CASE-5）：案件結案為失敗，時間軸記一筆（不 commit）。"""
    if case.closed_at is not None:
        return
    db.add(
        CaseUpdate(
            case_id=case.case_id,
            user_id=user.user_id,
            channel="other",
            contact_id=case.contact_id,
            result="lost",
            note="客戶要求退訂，不再聯絡",
            created_at=now,
        )
    )
    case.status = "lost"
    case.closed_at = now
    case.last_update_at = now
    case.next_follow_up = None


# ---------- 列表、詳情、匯出（F-CASE-4）----------
@dataclass(frozen=True)
class CaseFilter:
    status: str | None = None
    owner_id: int | None = None
    sent_from: date | None = None
    sent_to: date | None = None
    search: str | None = None
    queue: str | None = None
    case_ids: frozenset[int] | None = None  # 只看逾期時由呼叫端帶入（提醒條件在 view）
    reminders_only: bool = False
    page: int = 1
    page_size: int = 30


def _scoped(user: AppUser, f: CaseFilter) -> Select[SalesCase]:
    q = select(SalesCase)
    if f.search:
        q = q.join(Company, Company.company_id == SalesCase.company_id).where(
            SalesCase.case_no.ilike(f"%{f.search}%") | Company.name.ilike(f"%{f.search}%")
        )
    if not company_svc.is_manager(user):
        q = q.where(SalesCase.owner_id == user.user_id)
    elif f.owner_id is not None:
        q = q.where(SalesCase.owner_id == f.owner_id)
    if f.sent_from is not None:
        q = q.where(SalesCase.opened_at >= datetime.combine(f.sent_from, datetime.min.time(), TAIPEI))
    if f.sent_to is not None:
        end = datetime.combine(f.sent_to + timedelta(days=1), datetime.min.time(), TAIPEI)
        q = q.where(SalesCase.opened_at < end)
    if f.case_ids is not None and f.queue != "todo":
        q = q.where(SalesCase.case_id.in_(f.case_ids))
    if f.queue == "todo":
        if f.reminders_only:
            q = q.where(SalesCase.closed_at.is_(None), SalesCase.case_id.in_(f.case_ids or frozenset()))
        else:
            q = q.where(
                SalesCase.closed_at.is_(None),
                or_(
                    SalesCase.status.in_(("tracking", "replied", "negotiating", "no_response")),
                    SalesCase.case_id.in_(f.case_ids or frozenset()),
                ),
            )
    elif f.queue in {"overdue", "follow_up"} and f.case_ids is not None:
        q = q.where(SalesCase.case_id.in_(f.case_ids))
    return q


def _count(db: Session, q: Select[SalesCase]) -> int:
    return int(db.scalar(select(func.count()).select_from(q.subquery())) or 0)


def count_cases(db: Session, user: AppUser, f: CaseFilter) -> int:
    """只計算案件數，不載入資料列；給工作佇列摘要使用。"""
    q = _scoped(user, f)
    if f.status is not None:
        q = q.where(SalesCase.status == f.status)
    return _count(db, q)


def list_cases(db: Session, user: AppUser, f: CaseFilter) -> tuple[list[SalesCase], dict[str, int], int]:
    """回傳分頁案件、各狀態件數與目前篩選的總筆數。"""
    base = _scoped(user, f)
    counts_sub = base.subquery()
    counts: dict[str, int] = {
        r[0]: r[1] for r in db.execute(select(counts_sub.c.status, func.count()).group_by(counts_sub.c.status))
    }
    q = base
    if f.status is not None:
        q = q.where(SalesCase.status == f.status)
    total = _count(db, q)
    offset = max(f.page - 1, 0) * f.page_size
    cases = list(
        db.scalars(
            q.order_by(SalesCase.closed_at.is_not(None), SalesCase.next_follow_up, SalesCase.opened_at.desc())
            .offset(offset)
            .limit(f.page_size)
        )
    )
    return cases, {s: int(counts.get(s, 0)) for s in case_rules.CASE_STATUS_LABELS}, total


def timeline(db: Session, case_id: int) -> list[CaseUpdate]:
    q = select(CaseUpdate).where(CaseUpdate.case_id == case_id)
    return list(db.scalars(q.order_by(CaseUpdate.created_at, CaseUpdate.update_id)))


def export_csv(rows: Iterable[Mapping[str, object]]) -> str:
    """UTF-8 BOM，Excel 直接開不會亂碼。不放 email（個資只在系統裡看）。"""
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf)
    cols = ["case_no", "company_name", "status_label", "owner_name", "opened", "last", "next", "amount"]
    w.writerow(["案件編號", "公司", "狀態", "負責業務", "開案日", "最後回填", "下次追蹤日", "成交金額"])
    for r in rows:
        w.writerow([r[c] for c in cols])
    return buf.getvalue()
