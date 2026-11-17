"""案件追蹤：列表、詳情與時間軸、加入追蹤、人工回填、匯出（M3-09、F-CASE-1～4、F-REC-9）。

業務只看得到自己的案件；主管、管理員看全部（SPEC 6.2）。
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.config import Settings, get_settings
from app.db import get_db
from app.domain import case_rules
from app.models import AppUser, Company, Contact, SalesCase
from app.services import case_service, reminder_service

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
) -> case_service.CaseFilter:
    ids = frozenset(reminder_service.case_ids_with_reminders(db, user)) if overdue else None
    return case_service.CaseFilter(status=status, owner_id=owner, sent_from=sent_from, sent_to=sent_to, case_ids=ids)


@router.get("/cases", response_model=CaseList)
def list_cases(
    status: CaseStatus | None = None,
    owner: int | None = None,
    sent_from: date | None = None,
    sent_to: date | None = None,
    overdue: bool = False,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> CaseList:
    cases, counts = case_service.list_cases(db, user, _filter(db, user, owner, sent_from, sent_to, overdue, status))
    return CaseList(items=_rows(db, cases, _now()), counts=counts)


@router.get("/cases/export")
def export_cases(
    status: CaseStatus | None = None,
    owner: int | None = None,
    sent_from: date | None = None,
    sent_to: date | None = None,
    overdue: bool = False,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    cases, _ = case_service.list_cases(db, user, _filter(db, user, owner, sent_from, sent_to, overdue, status))
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


@router.post("/cases/{case_id}/updates", response_model=CaseDetail, status_code=201)
def add_update(
    case_id: int, body: UpdateBody, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
) -> CaseDetail:
    data = case_rules.UpdateInput(body.channel, body.result, body.note, body.next_follow_up, body.amount_twd)
    case = case_service.add_update(db, user, case_id, data, body.contact_id, _now())
    return _detail(db, case)
