"""案件追蹤：列表、詳情與時間軸、加入追蹤、人工回填、匯出（M3-09、F-CASE-1～4、F-REC-9）。

業務只看得到自己的案件；主管、管理員看全部（SPEC 6.2）。
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.config import Settings, get_settings
from app.db import get_db
from app.domain import case_rules
from app.domain.company_rules import DomainError
from app.models import AppUser, CaseUpdate, Company, Contact, SalesCase
from app.services import case_service, contact_service, reminder_service, sentiment_service

router = APIRouter()

CaseStatus = Literal["sent", "tracking", "replied", "negotiating", "no_response", "won", "lost"]


def _now() -> datetime:
    return datetime.now(UTC)


class CaseOut(BaseModel):
    case_id: int
    case_no: str
    company_id: int
    company_name: str
    company_status: str
    contact_id: int | None
    contact_name: str | None
    contact_email: str | None
    owner_id: int
    owner_name: str | None
    origin: str
    status: str
    opened_at: datetime
    last_update_at: datetime | None
    next_follow_up: date | None
    amount_twd: Decimal | None
    closed_at: datetime | None
    reminders: list[str]


class CaseList(BaseModel):
    items: list[CaseOut]
    counts: dict[str, int]
    total: int
    page: int
    page_size: int
    queue_counts: dict[str, int]


class UpdateOut(BaseModel):
    update_id: int
    user_name: str | None
    channel: str
    contact_name: str | None
    result: str
    note: str | None
    next_follow_up: date | None
    amount_twd: Decimal | None
    created_at: datetime
    sentiment: str | None = None  # positive / neutral / negative；沒備註或判斷失敗為 null（M4-07）
    sentiment_source: str | None = None  # ai / manual


class ContactOption(BaseModel):
    contact_id: int
    name: str | None
    email: str
    unsubscribed: bool


class CaseDetail(CaseOut):
    timeline: list[UpdateOut]
    contacts: list[ContactOption]


class TrackBody(BaseModel):
    company_ids: list[int] = Field(min_length=1, max_length=case_service.MAX_TRACK)


class UpdateBody(BaseModel):
    channel: Literal["email", "line", "wechat", "phone", "visit", "other"]
    result: Literal["replied", "negotiating", "won", "lost", "no_response"]
    note: str | None = Field(default=None, max_length=case_rules.MAX_NOTE)
    next_follow_up: date | None = None
    amount_twd: Decimal | None = Field(default=None, decimal_places=0)
    contact_id: int | None = None


def _rows(db: Session, cases: list[SalesCase], now: datetime) -> list[CaseOut]:
    if not cases:
        return []
    companies = {
        c.company_id: c
        for c in db.scalars(select(Company).where(Company.company_id.in_({x.company_id for x in cases})))
    }
    contact_ids = {x.contact_id for x in cases if x.contact_id}
    contacts = {c.contact_id: c for c in db.scalars(select(Contact).where(Contact.contact_id.in_(contact_ids)))}
    names = dict(db.execute(select(AppUser.user_id, AppUser.display_name)).all())
    reminders = reminder_service.kinds_by_case(db, [x.case_id for x in cases])
    out = []
    for x in cases:
        ct = contacts.get(x.contact_id) if x.contact_id else None
        co = companies[x.company_id]
        out.append(
            CaseOut(
                case_id=x.case_id,
                case_no=x.case_no,
                company_id=x.company_id,
                company_name=co.name,
                company_status=co.status,
                contact_id=x.contact_id,
                contact_name=ct.name if ct else None,
                contact_email=ct.email if ct else None,
                owner_id=x.owner_id,
                owner_name=names.get(x.owner_id),
                origin=x.origin,
                status=x.status,
                opened_at=x.opened_at,
                last_update_at=x.last_update_at,
                next_follow_up=x.next_follow_up,
                amount_twd=x.amount_twd,
                closed_at=x.closed_at,
                reminders=reminders.get(x.case_id, []),
            )
        )
    return out


def _detail(db: Session, case: SalesCase) -> CaseDetail:
    row = _rows(db, [case], _now())[0]
    names = dict(db.execute(select(AppUser.user_id, AppUser.display_name)).all())
    contacts = list(
        db.scalars(select(Contact).where(Contact.company_id == case.company_id).order_by(Contact.contact_id))
    )
    by_id = {c.contact_id: c for c in contacts}
    timeline = [
        UpdateOut(
            update_id=u.update_id,
            user_name=names.get(u.user_id) if u.user_id else None,
            channel=u.channel,
            contact_name=(by_id[u.contact_id].name or by_id[u.contact_id].email)
            if u.contact_id in by_id and u.contact_id
            else None,
            result=u.result,
            note=u.note,
            next_follow_up=u.next_follow_up,
            amount_twd=u.amount_twd,
            created_at=u.created_at,
            sentiment=u.sentiment,
            sentiment_source=u.sentiment_source,
        )
        for u in case_service.timeline(db, case.case_id)
    ]
    return CaseDetail(
        **row.model_dump(),
        timeline=timeline,
        contacts=[
            ContactOption(contact_id=c.contact_id, name=c.name, email=c.email, unsubscribed=c.unsubscribed)
            for c in contacts
        ],
    )


def _filter(
    db: Session,
    user: AppUser,
    owner: int | None,
    sent_from: date | None,
    sent_to: date | None,
    overdue: bool,
    status: str | None = None,
    search: str | None = None,
    queue: str | None = None,
    page: int = 1,
    page_size: int = 30,
) -> case_service.CaseFilter:
    ids: frozenset[int] | None = None
    reminders_only = overdue and queue not in {"overdue", "follow_up"}
    if queue == "todo":
        ids = frozenset(reminder_service.case_ids_with_reminders(db, user))
    elif overdue or queue == "overdue":
        ids = frozenset(reminder_service.case_ids_with_reminders(db, user, {"overdue_report"}))
    elif queue == "follow_up":
        ids = frozenset(reminder_service.case_ids_with_reminders(db, user, {"follow_up_due", "no_response"}))
    return case_service.CaseFilter(
        status=status,
        owner_id=owner,
        sent_from=sent_from,
        sent_to=sent_to,
        search=search.strip() or None if search else None,
        queue=queue,
        case_ids=ids,
        reminders_only=reminders_only,
        page=page,
        page_size=page_size,
    )


@router.get("/cases", response_model=CaseList)
def list_cases(
    status: CaseStatus | None = None,
    owner: int | None = None,
    sent_from: date | None = None,
    sent_to: date | None = None,
    overdue: bool = False,
    q: str | None = Query(default=None, max_length=100),
    queue: str | None = Query(default=None, pattern="^(todo|overdue|follow_up|all)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> CaseList:
    f = _filter(db, user, owner, sent_from, sent_to, overdue, status, q, queue, page, page_size)
    cases, counts, total = case_service.list_cases(db, user, f)
    base = _filter(db, user, owner, sent_from, sent_to, False, None, q, None, 1, 1)
    all_total = case_service.count_cases(db, user, base)
    todo = _filter(db, user, owner, sent_from, sent_to, False, None, q, "todo", 1, 1)
    todo_total = case_service.count_cases(db, user, todo)
    overdue_filter = _filter(db, user, owner, sent_from, sent_to, False, None, q, "overdue", 1, 1)
    overdue_total = case_service.count_cases(db, user, overdue_filter)
    follow_filter = _filter(db, user, owner, sent_from, sent_to, False, None, q, "follow_up", 1, 1)
    follow_total = case_service.count_cases(db, user, follow_filter)
    return CaseList(
        items=_rows(db, cases, _now()),
        counts=counts,
        total=total,
        page=page,
        page_size=page_size,
        queue_counts={"todo": todo_total, "overdue": overdue_total, "follow_up": follow_total, "all": all_total},
    )


@router.get("/cases/export")
def export_cases(
    status: CaseStatus | None = None,
    owner: int | None = None,
    sent_from: date | None = None,
    sent_to: date | None = None,
    overdue: bool = False,
    q: str | None = Query(default=None, max_length=100),
    queue: str | None = Query(default=None, pattern="^(todo|overdue|follow_up|all)$"),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    f = _filter(db, user, owner, sent_from, sent_to, overdue, status, q, queue, 1, 10000)
    cases, _, _ = case_service.list_cases(db, user, f)
    rows = [
        {
            "case_no": r.case_no,
            "company_name": r.company_name,
            "status_label": case_rules.CASE_STATUS_LABELS[r.status],
            "owner_name": r.owner_name or "",
            "opened": r.opened_at.astimezone(case_service.TAIPEI).date().isoformat(),
            "last": r.last_update_at.astimezone(case_service.TAIPEI).date().isoformat() if r.last_update_at else "",
            "next": r.next_follow_up.isoformat() if r.next_follow_up else "",
            "amount": str(r.amount_twd) if r.amount_twd is not None else "",
        }
        for r in _rows(db, cases, _now())
    ]
    return Response(
        content=case_service.export_csv(rows).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="cases.csv"'},
    )


@router.post("/cases", response_model=list[CaseOut], status_code=201)
def add_tracking(
    body: TrackBody,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[CaseOut]:
    cases = case_service.add_tracking(db, user, body.company_ids, _now(), settings.lock_days)
    return _rows(db, cases, _now())


@router.get("/cases/{case_id}", response_model=CaseDetail)
def get_case(case_id: int, user: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> CaseDetail:
    return _detail(db, case_service.get_case(db, user, case_id))


class UnsubscribeBody(BaseModel):
    contact_id: int | None = None  # 沒填就用案件的聯絡人
    whole_company: bool = False  # 客戶明講整家公司都不要聯絡（F-CASE-5）


@router.post("/cases/{case_id}/unsubscribe", response_model=CaseDetail)
def unsubscribe(
    case_id: int,
    body: UnsubscribeBody | None = None,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> CaseDetail:
    """客戶要求退訂（M3-04a、M3-17、F-CASE-5）：聯絡人退訂；整家公司不要聯絡或已沒有其他聯絡人時，
    公司改成不再聯絡、案件結案為失敗。否則案件照常進行，可以改用其他聯絡人。"""
    case = case_service.get_case(db, user, case_id)
    contact_id = (body.contact_id if body else None) or case.contact_id
    contact = db.get(Contact, contact_id) if contact_id else None
    if contact is None or contact.company_id != case.company_id:
        raise DomainError("NO_CONTACT", "請選擇要求退訂的聯絡人", 422)
    contact_service.unsubscribe(
        db, user, contact, f"案件 {case.case_no} 客戶要求退訂", whole_company=bool(body and body.whole_company)
    )
    db.refresh(case)
    return _detail(db, case)


class SentimentBody(BaseModel):
    sentiment: str  # positive / neutral / negative；合法值由 domain 檢查（INVALID_SENTIMENT）


@router.patch("/cases/{case_id}/updates/{update_id}/sentiment", response_model=CaseDetail)
def correct_sentiment(
    case_id: int,
    update_id: int,
    body: SentimentBody,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> CaseDetail:
    """M4-07c：業務手動修正客戶態度（寫 activity_log）。只有看得到這件案件的人可以改。"""
    case = case_service.get_case(db, user, case_id)
    update = db.get(CaseUpdate, update_id)
    if update is None or update.case_id != case.case_id:
        raise DomainError("UPDATE_NOT_FOUND", "找不到這筆回填紀錄", 404)
    sentiment_service.set_manual(db, user, update, body.sentiment, case.company_id)
    return _detail(db, case)


@router.post("/cases/{case_id}/updates", response_model=CaseDetail, status_code=201)
def add_update(
    case_id: int, body: UpdateBody, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
) -> CaseDetail:
    data = case_rules.UpdateInput(body.channel, body.result, body.note, body.next_follow_up, body.amount_twd)
    case = case_service.add_update(db, user, case_id, data, body.contact_id, _now())
    return _detail(db, case)
