"""產生草稿（M2-03c、M4-06c、M4-06i、M4-06j；F-MAIL-2、F-MAIL-3）。

三種模式：
- template_only：模板代入變數。
- template_ai：AI 只寫 {{ai_paragraph}} 那一段，其他照模板（M4-06c）。
- full_ai：AI 寫主旨與整封內文，結尾一律由系統補退訂說明（M4-06i）。
一封失敗不影響其他封：每封各自 commit，失敗的標成 failed 並記錄錯誤代碼（M4-06j）。
AI 呼叫可以同時進行（LLM_CONCURRENCY），但資料庫讀寫都在呼叫端的執行緒，session 不跨執行緒。
"""

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import ai_rules, draft_rules, template_rules
from app.domain.company_rules import DomainError
from app.models import AppUser, Campaign, Company, Contact, EmailDraft, EmailTemplate, v_recommendation
from app.services import ai_writer, campaign_service, site_service
from app.services.llm import LlmClient, LlmError, LlmResult

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


def _brief(db: Session, draft: EmailDraft, sender: AppUser) -> ai_writer.Brief:
    row = db.execute(
        select(v_recommendation.c.industry, v_recommendation.c.product_type, v_recommendation.c.reason).where(
            v_recommendation.c.company_id == draft.company_id
        )
    ).first()
    company = db.get(Company, draft.company_id)
    contact = db.get(Contact, draft.contact_id)
    return ai_writer.Brief(
        company_name=company.name if company else "",
        industry=row.industry if row else None,
        product_type=row.product_type if row else None,
        reason=row.reason if row else None,
        site_summary=site_service.usable_summary(db, draft.company_id),  # 沒有就留空，寫信改用推薦理由（M4-08e）
        contact_name=(contact.name if contact and contact.name else DEFAULT_CONTACT_NAME),
        sender_name=sender.display_name,
    )


@dataclass(frozen=True)
class AiOutcome:
    """一封 AI 呼叫的結果（在工作執行緒裡產生，不碰資料庫）。"""

    paragraph: ai_rules.AiParagraph | None = None
    mail: ai_rules.AiMail | None = None
    result: LlmResult | None = None
    error_code: str | None = None


def call_ai(llm: LlmClient, mode: str, brief: ai_writer.Brief) -> AiOutcome:
    try:
        if mode == "template_ai":
            paragraph, result = ai_writer.write_paragraph(llm, brief)
            return AiOutcome(paragraph=paragraph, result=result)
        mail, result = ai_writer.write_mail(llm, brief)
        return AiOutcome(mail=mail, result=result)
    except (DomainError, LlmError) as e:
        return AiOutcome(error_code=e.code)
    except Exception:  # 不認得的錯誤也只讓這一封失敗，不連累其他封
        log.exception("AI 產生發生未預期錯誤")
        return AiOutcome(error_code="AI_UNEXPECTED_ERROR")


def _fail(db: Session, draft: EmailDraft, code: str) -> None:
    draft.status = draft_rules.transition(draft.status, "failed")
    draft.last_error = code
    log.info("草稿產生失敗 draft=%s code=%s", draft.draft_id, code)
    db.commit()


def _fill(draft: EmailDraft, subject: str, body: str) -> None:
    draft.subject = subject
    draft.body_text = body
    draft.body_html = template_rules.text_to_html(body)
    draft.ai_original = body  # F-MAIL-8：一開始產生的內容，核准時比對業務改了多少
    draft.edit_ratio = None
    draft.last_error = None
    draft.status = draft_rules.transition(draft.status, "pending_review")


def generate_one(db: Session, draft: EmailDraft, campaign: Campaign, template: EmailTemplate, sender: AppUser) -> None:
    """模板代入一封（template_only）：成功 → pending_review；失敗 → failed（last_error 只放錯誤代碼）。會 commit。"""
    try:
        subject, body = template_rules.render(template.subject, template.body_text, values_for(db, draft, sender))
    except DomainError as e:
        _fail(db, draft, e.code)
        return
    draft.gen_provider = draft.gen_model = draft.prompt_version = None
    _fill(draft, subject, body)
    db.commit()


def apply_ai(
    db: Session,
    draft: EmailDraft,
    mode: str,
    template: EmailTemplate,
    sender: AppUser,
    outcome: AiOutcome,
) -> None:
    """把 AI 的結果寫進草稿：成功 → pending_review；失敗 → failed。會 commit。"""
    if outcome.error_code or outcome.result is None:
        _fail(db, draft, outcome.error_code or "AI_UNEXPECTED_ERROR")
        return
    try:
        if mode == "template_ai":
            assert outcome.paragraph is not None
            values = values_for(db, draft, sender)
            values["ai_paragraph"] = outcome.paragraph.ai_paragraph
            subject, body = template_rules.render(template.subject, template.body_text, values)
        else:
            assert outcome.mail is not None
            subject = outcome.mail.subject
            body = template_rules.ensure_unsubscribe(outcome.mail.body_text)  # 退訂說明一律由系統補
    except DomainError as e:
        _fail(db, draft, e.code)
        return
    draft.gen_provider = outcome.result.provider
    draft.gen_model = outcome.result.model
    draft.prompt_version = ai_writer.PROMPT_VERSION
    _fill(draft, subject, body)
    db.commit()


def _ensure_template_fits(mode: str, template: EmailTemplate) -> None:
    """template_ai 的模板一定要有 {{ai_paragraph}}，否則 AI 寫的段落不會出現在信裡。"""
    if mode == "template_ai" and "ai_paragraph" not in template_rules.variables_in(template.body_text):
        raise DomainError("TEMPLATE_NO_AI_PARAGRAPH", "模板內文沒有 {{ai_paragraph}}，不能用「模板＋AI 段落」", 422)


def run_generate_job(
    db: Session,
    payload: dict[str, object],
    *,
    llm_factory: Callable[[], LlmClient] | None = None,
    concurrency: int = 1,
) -> int:
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
    mode = campaign.gen_mode

    runnable: list[EmailDraft] = []
    for draft in drafts:
        if template is None or sender is None:
            _fail(db, draft, "TEMPLATE_NOT_FOUND")
        else:
            runnable.append(draft)

    if template is not None and sender is not None and runnable:
        if mode == "template_only":
            for draft in runnable:
                generate_one(db, draft, campaign, template, sender)
        else:
            _generate_ai(db, runnable, mode, template, sender, llm_factory, concurrency)
    campaign_service.refresh_status(db, campaign)
    db.commit()
    return len(drafts)


def _generate_ai(
    db: Session,
    drafts: list[EmailDraft],
    mode: str,
    template: EmailTemplate,
    sender: AppUser,
    llm_factory: Callable[[], LlmClient] | None,
    concurrency: int,
) -> None:
    try:
        _ensure_template_fits(mode, template)
        if llm_factory is None:
            raise LlmError("LLM_NOT_CONFIGURED")
        llm = llm_factory()
    except (DomainError, LlmError) as e:
        for draft in drafts:
            _fail(db, draft, e.code)
        return
    # 資料庫讀取先在這個執行緒做完；工作執行緒只呼叫 LLM
    briefs = {draft.draft_id: _brief(db, draft, sender) for draft in drafts}
    by_id = {draft.draft_id: draft for draft in drafts}
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures: dict[Future[AiOutcome], int] = {
            pool.submit(call_ai, llm, mode, briefs[d.draft_id]): d.draft_id for d in drafts
        }
        for future in as_completed(futures):
            apply_ai(db, by_id[futures[future]], mode, template, sender, future.result())
