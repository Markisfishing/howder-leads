"""產生草稿（M2-03c、F-MAIL-2、F-MAIL-3）。

M2 只有 template_only：模板代入變數。AI 模式在 M4 加進來（ADR 0006，LlmClient 介面）。
一封失敗不影響其他封：每封各自 commit，失敗的標成 failed 並記錄錯誤代碼。
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import draft_rules, template_rules
from app.domain.company_rules import DomainError
from app.models import AppUser, Campaign, Company, Contact, EmailDraft, EmailTemplate, v_recommendation
from app.services import campaign_service

log = logging.getLogger("howder.generator")

# 聯絡人沒有填姓名時的稱呼
DEFAULT_CONTACT_NAME = "採購負責人"


def values_for(db: Session, draft: EmailDraft, sender: AppUser) -> dict[str, str | None]:
    company = db.get(Company, draft.company_id)
    contact = db.get(Contact, draft.contact_id)
    industry = db.scalar(select(v_recommendation.c.industry).where(v_recommendation.c.company_id == draft.company_id))
    return {
        "company_name": company.name if company else None,
        "contact_name": (contact.name if contact and contact.name else DEFAULT_CONTACT_NAME),
        "contact_title": contact.title if contact else None,
        "industry": industry,
        "sender_name": sender.display_name,
        "sender_email": sender.email,
        "ai_paragraph": None,
    }


def generate_one(db: Session, draft: EmailDraft, campaign: Campaign, template: EmailTemplate, sender: AppUser) -> None:
    """產生一封：成功 → pending_review；失敗 → failed（last_error 只放錯誤代碼）。會 commit。"""
    try:
        if campaign.gen_mode != "template_only":
            raise DomainError("GEN_MODE_NOT_AVAILABLE", "AI 生成模式在 M4 開放", 422)
        subject, body = template_rules.render(template.subject, template.body_text, values_for(db, draft, sender))
    except DomainError as e:
        draft.status = draft_rules.transition(draft.status, "failed")
        draft.last_error = e.code
        log.info("草稿產生失敗 draft=%s code=%s", draft.draft_id, e.code)
    else:
        draft.subject = subject
        draft.body_text = body
        draft.body_html = template_rules.text_to_html(body)
        draft.ai_original = body  # F-MAIL-8：一開始產生的內容，核准時比對業務改了多少
        draft.edit_ratio = None
        draft.last_error = None
        draft.status = draft_rules.transition(draft.status, "pending_review")
    db.commit()


def run_generate_job(db: Session, payload: dict[str, object]) -> int:
    """worker handler：產生批次裡所有「產生中」的草稿（或 payload 指定的幾封）。回傳處理了幾封。"""
    campaign = db.get(Campaign, int(payload["campaign_id"]))  # type: ignore[call-overload]
    if campaign is None:
        return 0
    template = db.get(EmailTemplate, campaign.template_id) if campaign.template_id else None
    sender = db.get(AppUser, campaign.owner_id)
    stmt = select(EmailDraft).where(EmailDraft.campaign_id == campaign.campaign_id, EmailDraft.status == "generating")
    draft_ids = payload.get("draft_ids")
    if isinstance(draft_ids, list):
        stmt = stmt.where(EmailDraft.draft_id.in_([int(d) for d in draft_ids]))
    drafts = list(db.scalars(stmt.order_by(EmailDraft.draft_id)))
    for draft in drafts:
        if template is None or sender is None:
            draft.status = draft_rules.transition(draft.status, "failed")
            draft.last_error = "TEMPLATE_NOT_FOUND"
            db.commit()
            continue
        generate_one(db, draft, campaign, template, sender)
    campaign_service.refresh_status(db, campaign)
    db.commit()
    return len(drafts)
