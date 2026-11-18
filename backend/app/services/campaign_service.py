"""邀請信批次（M2-03b、F-MAIL-1、F-MAIL-7）。

建立批次時：只收「已通過」的公司、每家選一位聯絡人，先跑寄送防呆，
通過的公司改成「草稿已產生」(drafted)，再把產生草稿的工作排進佇列；API 只回傳 job_id。
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import send_guard
from app.domain.company_rules import DomainError
from app.models import AppUser, Campaign, Company, Contact, EmailDraft, EmailMessage, EmailTemplate, v_recommendation
from app.services import company_service as company_svc
from app.services import jobs

AVAILABLE_MODES = frozenset({"template_only"})  # template_ai / full_ai 在 M4（ADR 0006）
MAX_TARGETS = 200


@dataclass(frozen=True)
class Target:
    company_id: int
    contact_id: int | None


@dataclass(frozen=True)
class Excluded:
    company_id: int
    name: str
    reasons: list[str]


def last_sent_at(db: Session, company_id: int) -> datetime | None:
    """這家公司最近一次寄出的時間（任何業務、任何批次都算）。"""
    return db.scalar(
        select(func.max(EmailMessage.sent_at))
        .join(EmailDraft, EmailDraft.draft_id == EmailMessage.draft_id)
        .where(EmailDraft.company_id == company_id)
    )


def guard_input(db: Session, company: Company, contact: Contact | None) -> send_guard.GuardInput:
    return send_guard.GuardInput(
        company_status=company.status,
        owner=company_svc._ownership(company),
        contact_exists=contact is not None and contact.company_id == company.company_id,
        contact_unsubscribed=bool(contact and contact.unsubscribed),
        last_sent_at=last_sent_at(db, company.company_id),
    )


def can_view(user: AppUser, campaign: Campaign) -> bool:
    return campaign.owner_id == user.user_id or company_svc.is_manager(user)


def get_campaign(db: Session, user: AppUser, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or not can_view(user, campaign):
        raise DomainError("CAMPAIGN_NOT_FOUND", "找不到這個邀請信批次", 404)
    return campaign


def list_campaigns(db: Session, user: AppUser) -> list[Campaign]:
    stmt = select(Campaign).order_by(Campaign.created_at.desc(), Campaign.campaign_id.desc())
    if not company_svc.is_manager(user):
        stmt = stmt.where(Campaign.owner_id == user.user_id)
    return list(db.scalars(stmt))


def draft_counts(db: Session, campaign_ids: list[int]) -> dict[int, dict[str, int]]:
    """每個批次各狀態的草稿數（產生進度、預覽佇列用）。"""
    out: dict[int, dict[str, int]] = {cid: {} for cid in campaign_ids}
    if not campaign_ids:
        return out
    rows = db.execute(
        select(EmailDraft.campaign_id, EmailDraft.status, func.count())
        .where(EmailDraft.campaign_id.in_(campaign_ids))
        .group_by(EmailDraft.campaign_id, EmailDraft.status)
    )
    for cid, status, n in rows:
        out[cid][status] = n
    return out


def default_contact(contacts: list[Contact]) -> Contact | None:
    """沒指定聯絡人時寄給誰：第一位（最早建立）沒退訂的聯絡人。候選清單和建立批次共用。"""
    return next((ct for ct in sorted(contacts, key=lambda x: x.contact_id) if not ct.unsubscribed), None)


def candidates(
    db: Session, user: AppUser, now: datetime, *, company_ids: set[int] | None = None
) -> list[dict[str, object]]:
    """可以選進批次的公司：所有「已通過」的公司，附上聯絡人與不能寄的原因（給前端顯示）。

    company_ids 不是 None 時只回傳這些公司（M3-16：推薦清單篩選的結果）。
    """
    stmt = select(Company).where(Company.status == "approved").order_by(Company.name)
    if company_ids is not None:
        stmt = stmt.where(Company.company_id.in_(company_ids))
    companies = list(db.scalars(stmt))
    if not companies:
        return []
    ids = [c.company_id for c in companies]
    rec = {r.company_id: r for r in db.execute(select(v_recommendation).where(v_recommendation.c.company_id.in_(ids)))}
    contacts: dict[int, list[Contact]] = {}
    for ct in db.scalars(select(Contact).where(Contact.company_id.in_(ids)).order_by(Contact.contact_id)):
        contacts.setdefault(ct.company_id, []).append(ct)
    out: list[dict[str, object]] = []
    for c in companies:
        cts = contacts.get(c.company_id, [])
        default = default_contact(cts)
        reasons = send_guard.exclusions(guard_input(db, c, default), user.user_id, now, stage="draft")
        r = rec.get(c.company_id)
        out.append(
            {
                "company_id": c.company_id,
                "name": c.name,
                "stars": r.stars if r else None,
                "priority": r.priority if r else None,
                "industry": r.industry if r else None,
                "owner_name": r.owner_name if r else None,
                "contacts": [
                    {"contact_id": ct.contact_id, "name": ct.name, "email": ct.email, "unsubscribed": ct.unsubscribed}
                    for ct in cts
                ],
                "default_contact_id": default.contact_id if default else None,
                "reasons": reasons,
            }
        )
    # 可以寄的排前面，再依星級
    out.sort(key=lambda x: (bool(x["reasons"]), -(int(x["stars"] or 0))))  # type: ignore[call-overload]
    return out


def create_campaign(
    db: Session,
    user: AppUser,
    *,
    name: str,
    template_id: int,
    gen_mode: str,
    targets: list[Target],
    now: datetime,
) -> tuple[Campaign, int, list[Excluded]]:
    """建立批次。回傳 (批次, job_id, 被排除的公司與原因)。全部被排除時報錯，不建立空批次。"""
    if gen_mode not in AVAILABLE_MODES:
        raise DomainError("GEN_MODE_NOT_AVAILABLE", "AI 生成模式在 M4 開放，目前只能用模板", 422)
    if not name.strip():
        raise DomainError("CAMPAIGN_NAME_REQUIRED", "請填寫批次名稱", 422)
    if not targets:
        raise DomainError("NO_TARGETS", "請至少選一家公司", 422)
    if len(targets) > MAX_TARGETS:
        raise DomainError("TOO_MANY_TARGETS", f"一個批次最多 {MAX_TARGETS} 家", 422)
    if len({t.company_id for t in targets}) != len(targets):
        raise DomainError("DUPLICATE_TARGET", "同一家公司只能選一次", 422)
    template = db.get(EmailTemplate, template_id)
    if template is None or not template.is_active:
        raise DomainError("TEMPLATE_NOT_ACTIVE", "請選擇使用中的模板", 422)

    included: list[tuple[Company, Contact]] = []
    excluded: list[Excluded] = []
    companies = {
        c.company_id: c
        for c in db.scalars(
            select(Company).where(Company.company_id.in_([t.company_id for t in targets])).with_for_update()
        )
    }
    for t in targets:
        company = companies.get(t.company_id)
        if company is None:
            raise DomainError("COMPANY_NOT_FOUND", f"找不到公司 #{t.company_id}", 404)
        if t.contact_id:
            contact = db.get(Contact, t.contact_id)
        else:
            contact = default_contact(list(db.scalars(select(Contact).where(Contact.company_id == company.company_id))))
        reasons = send_guard.exclusions(guard_input(db, company, contact), user.user_id, now, stage="draft")
        if contact is not None and contact.company_id != company.company_id:
            reasons = ["CONTACT_NOT_IN_COMPANY", *[r for r in reasons if r != "NO_CONTACT"]]
        if reasons:
            excluded.append(Excluded(company.company_id, company.name, reasons))
        else:
            assert contact is not None
            included.append((company, contact))
    if not included:
        db.rollback()
        detail = "；".join(f"{e.name}：{send_guard.describe(e.reasons)}" for e in excluded[:5])
        raise DomainError("NO_ELIGIBLE_TARGETS", f"選的公司都不能寄：{detail}", 422)

    campaign = Campaign(
        name=name.strip(),
        template_id=template.template_id,
        gen_mode=gen_mode,
        owner_id=user.user_id,
        status="generating",
    )
    db.add(campaign)
    db.flush()
    for company, contact in included:
        db.add(
            EmailDraft(
                campaign_id=campaign.campaign_id,
                company_id=company.company_id,
                contact_id=contact.contact_id,
                status="generating",
            )
        )
        company_svc.change_status(db, company, "drafted", user, f"邀請信批次 #{campaign.campaign_id}")
    job = jobs.enqueue(db, "generate_drafts", {"campaign_id": campaign.campaign_id}, created_by=user.user_id)
    db.commit()
    return campaign, job.job_id, excluded


def refresh_status(db: Session, campaign: Campaign) -> None:
    """依草稿狀態更新批次狀態（不 commit）。

    還有待審核或失敗的草稿 → reviewing（待審核）；都審完、有核准但還沒按寄出 → ready（待寄出，M2-16）；
    按寄出後 → scheduled／sending；沒有要寄的 → done。
    """
    counts = draft_counts(db, [campaign.campaign_id])[campaign.campaign_id]
    if counts.get("generating"):
        campaign.status = "generating"
        return
    waiting = counts.get("pending_review", 0) + counts.get("failed", 0)
    approved = counts.get("approved", 0)
    scheduled = db.scalar(
        select(func.count())
        .select_from(EmailDraft)
        .where(
            EmailDraft.campaign_id == campaign.campaign_id,
            EmailDraft.status == "approved",
            EmailDraft.scheduled_at.is_not(None),
        )
    )
    if scheduled:
        campaign.status = "sending" if counts.get("sent") else "scheduled"
    elif waiting:
        campaign.status = "reviewing"
    elif approved:
        campaign.status = "ready"
    else:
        campaign.status = "done"
