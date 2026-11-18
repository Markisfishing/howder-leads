"""邀請信批次、預覽佇列、寄出（M2-03、M2-05、M2-07）。耗時工作都排進佇列，API 只回傳 job_id。"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.v1.companies import ListFilters, apply_filters, has_filters, list_filters
from app.config import Settings, get_settings
from app.db import get_db
from app.domain.send_guard import REASON_LABELS
from app.models import AppUser, Campaign, Company, Contact, EmailDraft, EmailTemplate, v_recommendation
from app.services import campaign_service, draft_service, send_service

router = APIRouter()


def _now() -> datetime:
    return datetime.now(UTC)


# ---------- 回應 ----------
class Progress(BaseModel):
    total: int
    generating: int
    pending_review: int
    approved: int
    scheduled: int
    sent: int
    failed: int
    discarded: int


class CampaignOut(BaseModel):
    campaign_id: int
    name: str
    status: str
    gen_mode: str
    template_id: int | None
    template_name: str | None
    template_version: int | None
    owner_id: int
    owner_name: str | None
    scheduled_at: datetime | None
    created_at: datetime
    progress: Progress


class ContactOption(BaseModel):
    contact_id: int
    name: str | None
    email: str
    unsubscribed: bool


class Candidate(BaseModel):
    company_id: int
    name: str
    stars: int | None
    priority: str | None
    industry: str | None
    owner_name: str | None
    contacts: list[ContactOption]
    default_contact_id: int | None
    reasons: list[str]


class ExcludedOut(BaseModel):
    company_id: int
    name: str
    reasons: list[str]


class CreateOut(BaseModel):
    campaign: CampaignOut
    job_id: int
    excluded: list[ExcludedOut]


class DraftOut(BaseModel):
    draft_id: int
    campaign_id: int
    company_id: int
    company_name: str
    contact_id: int
    contact_name: str | None
    contact_email: str
    subject: str
    body_text: str
    status: str
    edit_ratio: Decimal | None
    scheduled_at: datetime | None
    send_attempts: int
    last_error: str | None
    approved_at: datetime | None


class DraftPageOut(BaseModel):
    items: list[DraftOut]
    total: int
    page: int
    page_size: int
    status_counts: dict[str, int]


class SendOut(BaseModel):
    scheduled: int
    blocked: list[dict[str, object]]
    campaign: CampaignOut


# ---------- 請求 ----------
class TargetIn(BaseModel):
    company_id: int
    contact_id: int | None = None


class CampaignCreate(BaseModel):
    name: str = Field(max_length=100)
    template_id: int
    gen_mode: Literal["template_only", "template_ai", "full_ai"] = "template_only"
    targets: list[TargetIn] = Field(max_length=campaign_service.MAX_TARGETS)


class DraftPatch(BaseModel):
    subject: str | None = Field(default=None, max_length=200)
    body_text: str | None = Field(default=None, max_length=20000)


class ConfirmBody(BaseModel):
    confirm: bool = False


class SendBody(BaseModel):
    scheduled_at: datetime | None = None


# ---------- 組回應 ----------
def _campaign_out(db: Session, campaigns: list[Campaign]) -> list[CampaignOut]:
    ids = [c.campaign_id for c in campaigns]
    counts = campaign_service.draft_counts(db, ids)
    sched_count: dict[int, int] = {}  # 已核准而且已排程（等 worker 寄出）的封數
    for row in db.execute(
        select(EmailDraft.campaign_id).where(
            EmailDraft.campaign_id.in_(ids), EmailDraft.status == "approved", EmailDraft.scheduled_at.is_not(None)
        )
    ):
        sched_count[row[0]] = sched_count.get(row[0], 0) + 1
    templates = {
        t.template_id: t
        for t in db.scalars(
            select(EmailTemplate).where(
                EmailTemplate.template_id.in_([c.template_id for c in campaigns if c.template_id])
            )
        )
    }
    names = dict(db.execute(select(AppUser.user_id, AppUser.display_name)).all())
    out = []
    for c in campaigns:
        k = counts.get(c.campaign_id, {})
        n_sched = sched_count.get(c.campaign_id, 0)
        t = templates.get(c.template_id) if c.template_id else None
        out.append(
            CampaignOut(
                campaign_id=c.campaign_id,
                name=c.name,
                status=c.status,
                gen_mode=c.gen_mode,
                template_id=c.template_id,
                template_name=t.name if t else None,
                template_version=t.version if t else None,
                owner_id=c.owner_id,
                owner_name=names.get(c.owner_id),
                scheduled_at=c.scheduled_at,
                created_at=c.created_at,
                progress=Progress(
                    total=sum(k.values()),
                    generating=k.get("generating", 0),
                    pending_review=k.get("pending_review", 0),
                    approved=k.get("approved", 0) - n_sched,
                    scheduled=n_sched,
                    sent=k.get("sent", 0),
                    failed=k.get("failed", 0),
                    discarded=k.get("discarded", 0),
                ),
            )
        )
    return out


def _one(db: Session, campaign: Campaign) -> CampaignOut:
    return _campaign_out(db, [campaign])[0]


def _draft_out(db: Session, drafts: list[EmailDraft]) -> list[DraftOut]:
    companies = dict(
        db.execute(
            select(Company.company_id, Company.name).where(Company.company_id.in_({d.company_id for d in drafts}))
        ).all()
    )
    contacts = {
        c.contact_id: c
        for c in db.scalars(select(Contact).where(Contact.contact_id.in_({d.contact_id for d in drafts})))
    }
    out = []
    for d in drafts:
        ct = contacts.get(d.contact_id)
        out.append(
            DraftOut(
                draft_id=d.draft_id,
                campaign_id=d.campaign_id,
                company_id=d.company_id,
                company_name=companies.get(d.company_id, ""),
                contact_id=d.contact_id,
                contact_name=ct.name if ct else None,
                contact_email=ct.email if ct else "",
                subject=d.subject,
                body_text=d.body_text,
                status=d.status,
                edit_ratio=d.edit_ratio,
                scheduled_at=d.scheduled_at,
                send_attempts=d.send_attempts,
                last_error=d.last_error,
                approved_at=d.approved_at,
            )
        )
    return out


# ---------- 批次 ----------
@router.get("/campaigns", response_model=list[CampaignOut])
def list_campaigns(user: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> list[CampaignOut]:
    return _campaign_out(db, campaign_service.list_campaigns(db, user))


@router.get("/campaigns/candidates", response_model=list[Candidate])
def list_candidates(
    filters: ListFilters = Depends(list_filters),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[Candidate]:
    """候選公司（M3-16）：沿用推薦清單的篩選參數（q 公司名稱／統編、industry_id、stars、min_stars…）。"""
    ids: set[int] | None = None
    if has_filters(filters):
        ids = set(db.scalars(apply_filters(select(v_recommendation.c.company_id), user, filters)))
    return [Candidate.model_validate(c) for c in campaign_service.candidates(db, user, _now(), company_ids=ids)]


@router.get("/campaigns/exclusion-reasons", response_model=dict[str, str])
def exclusion_reasons(_: AppUser = Depends(current_user)) -> dict[str, str]:
    return REASON_LABELS


@router.post("/campaigns", response_model=CreateOut, status_code=201)
def create_campaign(
    body: CampaignCreate, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
) -> CreateOut:
    campaign, job_id, excluded = campaign_service.create_campaign(
        db,
        user,
        name=body.name,
        template_id=body.template_id,
        gen_mode=body.gen_mode,
        targets=[campaign_service.Target(t.company_id, t.contact_id) for t in body.targets],
        now=_now(),
    )
    return CreateOut(
        campaign=_one(db, campaign),
        job_id=job_id,
        excluded=[ExcludedOut(company_id=e.company_id, name=e.name, reasons=e.reasons) for e in excluded],
    )


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: int, user: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> CampaignOut:
    return _one(db, campaign_service.get_campaign(db, user, campaign_id))


@router.get("/campaigns/{campaign_id}/drafts", response_model=DraftPageOut)
def list_drafts(
    campaign_id: int,
    q: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, max_length=30),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=50),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> DraftPageOut:
    campaign_service.get_campaign(db, user, campaign_id)
    base = (
        select(EmailDraft)
        .join(Company, Company.company_id == EmailDraft.company_id)
        .join(Contact, Contact.contact_id == EmailDraft.contact_id)
        .where(EmailDraft.campaign_id == campaign_id)
    )
    if q and q.strip():
        term = f"%{q.strip()}%"
        base = base.where(or_(Company.name.ilike(term), Contact.name.ilike(term), Contact.email.ilike(term)))
    if status and status in {"generating", "pending_review", "approved", "discarded", "sent", "failed"}:
        base = base.where(EmailDraft.status == status)

    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    drafts = list(db.scalars(base.order_by(EmailDraft.draft_id).offset((page - 1) * page_size).limit(page_size)))
    counts = {
        row.status: int(row.count)
        for row in db.execute(
            select(EmailDraft.status, func.count())
            .where(EmailDraft.campaign_id == campaign_id)
            .group_by(EmailDraft.status)
        )
    }
    return DraftPageOut(items=_draft_out(db, drafts), total=total, page=page, page_size=page_size, status_counts=counts)


@router.post("/campaigns/{campaign_id}/approve-all", response_model=CampaignOut)
def approve_all(
    campaign_id: int, body: ConfirmBody, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
) -> CampaignOut:
    draft_service.approve_all(db, user, campaign_id, confirm=body.confirm, now=_now())
    return _one(db, campaign_service.get_campaign(db, user, campaign_id))


@router.post("/campaigns/{campaign_id}/send", response_model=SendOut)
def send_campaign(
    campaign_id: int,
    body: SendBody,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SendOut:
    n, blocked = send_service.schedule_campaign(
        db, user, campaign_id, scheduled_at=body.scheduled_at, now=_now(), settings=settings
    )
    return SendOut(
        scheduled=n, blocked=blocked, campaign=_one(db, campaign_service.get_campaign(db, user, campaign_id))
    )


# ---------- 草稿 ----------
def _draft(db: Session, draft: EmailDraft) -> DraftOut:
    return _draft_out(db, [draft])[0]


@router.patch("/drafts/{draft_id}", response_model=DraftOut)
def patch_draft(
    draft_id: int, body: DraftPatch, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
) -> DraftOut:
    return _draft(db, draft_service.update_content(db, user, draft_id, subject=body.subject, body_text=body.body_text))


@router.post("/drafts/{draft_id}/approve", response_model=DraftOut)
def approve_draft(draft_id: int, user: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> DraftOut:
    return _draft(db, draft_service.approve(db, user, draft_id, _now()))


@router.post("/drafts/{draft_id}/unapprove", response_model=DraftOut)
def unapprove_draft(draft_id: int, user: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> DraftOut:
    return _draft(db, draft_service.unapprove(db, user, draft_id))


@router.post("/drafts/{draft_id}/discard", response_model=DraftOut)
def discard_draft(draft_id: int, user: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> DraftOut:
    return _draft(db, draft_service.discard(db, user, draft_id))


class JobOut(BaseModel):
    job_id: int


@router.post("/drafts/{draft_id}/regenerate", response_model=JobOut, status_code=202)
def regenerate_draft(draft_id: int, user: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> JobOut:
    return JobOut(job_id=draft_service.regenerate(db, user, draft_id))
