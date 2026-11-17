"""預覽佇列：修改、核准、取消核准、丟棄、重新產生、全部核准（M2-05a、M2-05c、M2-08a）。

草稿和公司狀態一起變：
- 核准：公司 drafted → draft_approved
- 取消核准：draft_approved → drafted
- 丟棄：公司退回 approved（之後可以再選進別的批次）
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import draft_rules, template_rules
from app.domain.company_rules import DomainError
from app.models import AppUser, Campaign, Company, EmailDraft
from app.services import campaign_service, jobs
from app.services import company_service as company_svc


def get_draft(db: Session, user: AppUser, draft_id: int, *, lock: bool = False) -> tuple[EmailDraft, Campaign]:
    stmt = select(EmailDraft).where(EmailDraft.draft_id == draft_id)
    if lock:
        stmt = stmt.with_for_update()
    draft = db.scalar(stmt)
    if draft is None:
        raise DomainError("DRAFT_NOT_FOUND", "找不到這封草稿", 404)
    campaign = campaign_service.get_campaign(db, user, draft.campaign_id)
    return draft, campaign


def _ensure_can_review(user: AppUser, campaign: Campaign) -> None:
    """批次的負責業務或主管可以審核。"""
    if campaign.owner_id != user.user_id and not company_svc.is_manager(user):
        raise DomainError("FORBIDDEN", "只有這個批次的負責業務或主管可以審核", 403)


def _company(db: Session, draft: EmailDraft) -> Company:
    return company_svc.get_company(db, draft.company_id)


def _move_company(db: Session, company: Company, target: str, user: AppUser, note: str) -> None:
    """公司狀態跟著草稿走；公司已經被改成 do_not_contact 等狀態時就不動。"""
    if company.status == target:
        return
    from app.domain import company_rules

    if company_rules.can_transition(company.status, target):
        company_svc.change_status(db, company, target, user, note)


def update_content(
    db: Session, user: AppUser, draft_id: int, *, subject: str | None, body_text: str | None
) -> EmailDraft:
    draft, campaign = get_draft(db, user, draft_id, lock=True)
    _ensure_can_review(user, campaign)
    draft_rules.ensure_editable(draft.status)
    if subject is not None:
        clean = " ".join(subject.split())
        if not clean:
            raise DomainError("DRAFT_SUBJECT_REQUIRED", "主旨不能空白", 422)
        draft.subject = clean
    if body_text is not None:
        if not body_text.strip():
            raise DomainError("DRAFT_BODY_REQUIRED", "內文不能空白", 422)
        # 業務刪掉退訂說明也會補回來（SPEC 7.5）
        draft.body_text = template_rules.ensure_unsubscribe(body_text.strip())
        draft.body_html = template_rules.text_to_html(draft.body_text)
    if draft.status == "failed":
        draft.status = draft_rules.transition(draft.status, "pending_review")
        draft.last_error = None
    db.commit()
    return draft


def _approve(db: Session, user: AppUser, draft: EmailDraft, now: datetime) -> None:
    draft.status = draft_rules.transition(draft.status, "approved")
    draft.edit_ratio = draft_rules.edit_ratio(draft.ai_original, draft.body_text)  # F-MAIL-8
    draft.approved_by = user.user_id
    draft.approved_at = now
    draft.last_error = None
    _move_company(db, _company(db, draft), "draft_approved", user, f"草稿 #{draft.draft_id} 核准")


def approve(db: Session, user: AppUser, draft_id: int, now: datetime) -> EmailDraft:
    draft, campaign = get_draft(db, user, draft_id, lock=True)
    _ensure_can_review(user, campaign)
    _approve(db, user, draft, now)
    campaign_service.refresh_status(db, campaign)
    db.commit()
    return draft


def approve_all(db: Session, user: AppUser, campaign_id: int, *, confirm: bool, now: datetime) -> int:
    """F-MAIL-4：全部核准要再確認一次（confirm=true），只核准「待審核」的草稿。"""
    campaign = campaign_service.get_campaign(db, user, campaign_id)
    _ensure_can_review(user, campaign)
    if not confirm:
        raise DomainError("CONFIRM_REQUIRED", "全部核准前請再確認一次", 422)
    drafts = list(
        db.scalars(
            select(EmailDraft)
            .where(EmailDraft.campaign_id == campaign_id, EmailDraft.status == "pending_review")
            .with_for_update()
        )
    )
    for draft in drafts:
        _approve(db, user, draft, now)
    campaign_service.refresh_status(db, campaign)
    db.commit()
    return len(drafts)


def unapprove(db: Session, user: AppUser, draft_id: int) -> EmailDraft:
    """取消核准（也會取消排程；排好的寄送工作執行時看到不是 approved 就會跳過）。"""
    draft, campaign = get_draft(db, user, draft_id, lock=True)
    _ensure_can_review(user, campaign)
    draft.status = draft_rules.transition(draft.status, "pending_review")
    draft.approved_by = None
    draft.approved_at = None
    draft.scheduled_at = None
    draft.edit_ratio = None
    _move_company(db, _company(db, draft), "drafted", user, f"草稿 #{draft.draft_id} 取消核准")
    campaign_service.refresh_status(db, campaign)
    db.commit()
    return draft


def discard(db: Session, user: AppUser, draft_id: int) -> EmailDraft:
    draft, campaign = get_draft(db, user, draft_id, lock=True)
    _ensure_can_review(user, campaign)
    draft.status = draft_rules.transition(draft.status, "discarded")
    draft.scheduled_at = None
    company = _company(db, draft)
    note = f"草稿 #{draft.draft_id} 丟棄"
    _move_company(db, company, "drafted", user, note)  # draft_approved → drafted
    _move_company(db, company, "approved", user, note)  # drafted → approved
    campaign_service.refresh_status(db, campaign)
    db.commit()
    return draft


def regenerate(db: Session, user: AppUser, draft_id: int) -> int:
    """重新產生一封：回到「產生中」並排進佇列，回傳 job_id。"""
    draft, campaign = get_draft(db, user, draft_id, lock=True)
    _ensure_can_review(user, campaign)
    if draft.status == "approved":
        raise DomainError("DRAFT_NOT_EDITABLE", "已核准的草稿要先取消核准才能重新產生", 409)
    draft.status = draft_rules.transition(draft.status, "generating")
    draft.last_error = None
    job = jobs.enqueue(
        db,
        "generate_drafts",
        {"campaign_id": campaign.campaign_id, "draft_ids": [draft.draft_id]},
        created_by=user.user_id,
    )
    campaign.status = "generating"
    db.commit()
    return job.job_id
