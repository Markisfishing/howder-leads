"""寄出（M2-04b、M2-06a、M2-07d、M2-07e）。

安全規則（CLAUDE.md 第 6 節）：
- 系統不會自動寄信：只有業務按「寄出」才會排程，而且只排「已核准」的草稿。
- worker 真正寄出前，在 domain 再檢查一次「是否已核准」和寄送防呆。
- 寄件人一定是批次的負責業務本人，主管也不能用別人的信箱寄。
"""

import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain import company_rules, draft_rules, send_limits
from app.domain.company_rules import DomainError, Ownership, can_transition
from app.models import ActivityLog, AppUser, Campaign, Company, Contact, EmailDraft, EmailMessage, UserMailCredential
from app.services import campaign_service, case_service, jobs
from app.services import company_service as company_svc
from app.services.mailer import MailAuthError, Mailer, MailSendError, OutgoingMail

log = logging.getLogger("howder.send")


def ensure_mail_ready(db: Session, user: AppUser, settings: Settings) -> None:
    """live＋Graph 要先連結 Outlook；sandbox 與共用 SMTP 信箱（ADR 0008）不需要。"""
    if settings.mail_mode != "live" or settings.mail_transport == "smtp":
        return
    cred = db.get(UserMailCredential, user.user_id)
    if cred is None:
        raise DomainError("MAIL_NOT_CONNECTED", "請先連結 Outlook 才能寄信", 409)
    if cred.status != "connected":
        raise DomainError("MAIL_AUTH_REQUIRED", "Outlook 連結已失效，請重新連結", 409)


def _count_for_day(db: Session, sender_id: int, day_start: datetime, day_end: datetime) -> int:
    """寄件人這一天已寄出＋已排定的封數（算每日上限）。"""
    sent = db.scalar(
        select(func.count())
        .select_from(EmailMessage)
        .where(EmailMessage.sender_id == sender_id, EmailMessage.sent_at >= day_start, EmailMessage.sent_at < day_end)
    )
    scheduled = db.scalar(
        select(func.count())
        .select_from(EmailDraft)
        .join(Campaign, Campaign.campaign_id == EmailDraft.campaign_id)
        .where(
            Campaign.owner_id == sender_id,
            EmailDraft.status == "approved",
            EmailDraft.scheduled_at >= day_start,
            EmailDraft.scheduled_at < day_end,
        )
    )
    return int(sent or 0) + int(scheduled or 0)


def _mark_failed(db: Session, draft: EmailDraft, code: str, user: AppUser | None) -> None:
    """M2-07e：寄不出去的草稿標成 failed，批次頁會顯示給寄件業務。"""
    if draft.status != "approved":
        return
    draft.status = draft_rules.transition(draft.status, "failed")
    draft.last_error = code
    draft.scheduled_at = None
    company = db.get(Company, draft.company_id)
    if company is not None:
        db.add(
            ActivityLog(
                company_id=company.company_id,
                user_id=user.user_id if user else None,
                action="send_failed",
                to_value=f"draft:{draft.draft_id}",
                note=code,
            )
        )
        if can_transition(company.status, "drafted") and company.status == "draft_approved":
            company_svc.change_status(db, company, "drafted", user, f"草稿 #{draft.draft_id} 寄送失敗")


def schedule_campaign(
    db: Session,
    user: AppUser,
    campaign_id: int,
    *,
    scheduled_at: datetime | None,
    now: datetime,
    settings: Settings,
) -> tuple[int, list[dict[str, object]]]:
    """業務按「寄出」：把已核准、還沒排程的草稿排進佇列。回傳 (排了幾封, 被防呆擋下的草稿)。"""
    campaign = campaign_service.get_campaign(db, user, campaign_id)
    if campaign.owner_id != user.user_id:
        raise DomainError("SEND_OWNER_ONLY", "信會從寄件人本人的信箱寄出，只有批次的負責業務可以寄", 403)
    ensure_mail_ready(db, user, settings)
    if scheduled_at is not None and scheduled_at < now:
        raise DomainError("SCHEDULE_IN_PAST", "排程時間不能早於現在", 422)
    drafts = list(
        db.scalars(
            select(EmailDraft)
            .where(
                EmailDraft.campaign_id == campaign_id,
                EmailDraft.status == "approved",
                EmailDraft.scheduled_at.is_(None),
            )
            .order_by(EmailDraft.draft_id)
            .with_for_update()
        )
    )
    if not drafts:
        raise DomainError("NOTHING_TO_SEND", "沒有已核准、等待寄出的草稿", 409)

    blocked: list[dict[str, object]] = []
    ready: list[EmailDraft] = []
    for draft in drafts:
        draft_rules.ensure_sendable(draft.status)
        company = company_svc.get_company(db, draft.company_id)
        contact = db.get(Contact, draft.contact_id)
        reasons = campaign_service.exclusions_for(db, company, contact, user.user_id, now, settings, stage="send")
        if reasons:
            _mark_failed(db, draft, "GUARD:" + ",".join(reasons), user)
            blocked.append({"draft_id": draft.draft_id, "company_name": company.name, "reasons": reasons})
        else:
            ready.append(draft)

    if ready:
        start = max(scheduled_at or now, now)
        day_start, day_end = send_limits.day_bounds(send_limits.local_day(start))
        times = send_limits.plan_send_times(
            len(ready),
            start=start,
            already_today=_count_for_day(db, user.user_id, day_start, day_end),
            daily_limit=settings.daily_send_limit,
            per_minute=settings.send_per_minute,
            day_start_hour=settings.send_day_start_hour,
            day_end_hour=settings.send_day_end_hour,
        )
        for draft, at in zip(ready, times, strict=True):
            draft.scheduled_at = at
            draft.last_error = None
            jobs.enqueue(db, "send_email", {"draft_id": draft.draft_id}, run_after=at, created_by=user.user_id)
        campaign.scheduled_at = times[0]
        db.add(
            ActivityLog(
                user_id=user.user_id,
                action="campaign_send",
                to_value=f"campaign:{campaign_id}",
                note=f"{len(ready)} 封",
            )
        )
    campaign_service.refresh_status(db, campaign)
    db.commit()
    return len(ready), blocked


def send_one(db: Session, draft_id: int, mailer: Mailer, settings: Settings, now: datetime) -> str:
    """worker handler：寄出一封。回傳 sent / skipped。

    - 不是 approved（期間被取消核准或丟棄）→ skipped，不寄。
    - 防呆沒過（期間退訂、被別人認領、14 天內有人寄過）→ 草稿標 failed，不寄。
    - 寄件人今天已達上限 → 丟 jobs.Reschedule，隔天再寄。
    - 暫時性錯誤 → 丟 jobs.JobError 讓佇列重試；權杖失效 → 暫停並請業務重新連結。
    """
    draft = db.scalar(select(EmailDraft).where(EmailDraft.draft_id == draft_id).with_for_update())
    if draft is None or draft.status != "approved":
        db.rollback()
        return "skipped"
    draft_rules.ensure_sendable(draft.status)  # F-MAIL-5：寄出前在後端再檢查一次
    campaign = db.get(Campaign, draft.campaign_id)
    company = db.get(Company, draft.company_id)
    contact = db.get(Contact, draft.contact_id)
    sender = db.get(AppUser, campaign.owner_id) if campaign else None
    if campaign is None or company is None or sender is None:
        db.rollback()
        return "skipped"

    # 呼叫 Graph 前最後一次檢查（含測試收件者白名單 M2-18）
    reasons = campaign_service.exclusions_for(db, company, contact, sender.user_id, now, settings, stage="send")
    if reasons or contact is None:
        _mark_failed(db, draft, "GUARD:" + ",".join(reasons or ["NO_CONTACT"]), None)
        campaign_service.refresh_status(db, campaign)
        db.commit()
        return "skipped"

    day_start, day_end = send_limits.day_bounds(send_limits.local_day(now))
    sent_today = db.scalar(
        select(func.count())
        .select_from(EmailMessage)
        .where(
            EmailMessage.sender_id == sender.user_id,
            EmailMessage.sent_at >= day_start,
            EmailMessage.sent_at < day_end,
        )
    )
    if int(sent_today or 0) >= settings.daily_send_limit or send_limits.is_after_hours(now, settings.send_day_end_hour):
        run_after = send_limits.next_day_start(now, settings.send_day_start_hour)
        draft.scheduled_at = run_after
        db.commit()
        raise jobs.Reschedule(run_after)

    mail = OutgoingMail(
        draft_id=draft.draft_id,
        sender_user_id=sender.user_id,
        to_email=contact.email,
        subject=draft.subject,
        body_html=draft.body_html,
    )
    draft.send_attempts += 1
    try:
        result = mailer.send(mail)
    except MailAuthError as e:
        # ADR 0005：權杖失效 → 暫停（取消排程），業務重新連結後再按寄出
        draft.scheduled_at = None
        draft.last_error = e.code
        campaign_service.refresh_status(db, campaign)
        db.commit()
        return "paused"
    except MailSendError as e:
        draft.last_error = e.code
        db.commit()
        raise jobs.JobError(e.code, retryable=e.retryable) from e

    message = EmailMessage(
        draft_id=draft.draft_id,
        sender_id=sender.user_id,
        graph_message_id=result.graph_message_id,
        conversation_id=result.conversation_id,
        sent_at=now,
    )
    db.add(message)
    db.flush()
    draft.status = draft_rules.transition(draft.status, "sent")
    draft.last_error = None
    if can_transition(company.status, "sent"):
        company_svc.change_status(db, company, "sent", sender, f"邀請信已寄出（草稿 #{draft.draft_id}）")
    if company.owner_id is None:
        # 寄出邀請信就是開始經營這家公司：沒人負責時順便認領，鎖定期間其他業務不能再寄（SPEC 11-11）
        owner = company_rules.claim(Ownership(None, None), sender.user_id, now, settings.lock_days)
        company.owner_id, company.owner_locked_until = owner.owner_id, owner.locked_until
        company_svc.log(db, company, sender, "claim", None, str(sender.user_id), "寄出邀請信時認領")
    case_service.open_for_email(db, company, draft.contact_id, sender, message, now)  # F-CASE-1
    db.add(
        ActivityLog(
            company_id=company.company_id, user_id=sender.user_id, action="send", to_value=f"draft:{draft.draft_id}"
        )
    )
    campaign_service.refresh_status(db, campaign)
    db.commit()
    log.info("已寄出 draft=%s mode=%s", draft.draft_id, settings.mail_mode)
    return "sent"


def mark_send_failed(db: Session, draft_id: int, code: str) -> None:
    """佇列重試都失敗後呼叫（M2-07e）。"""
    draft = db.scalar(select(EmailDraft).where(EmailDraft.draft_id == draft_id).with_for_update())
    if draft is None:
        return
    _mark_failed(db, draft, code, None)
    campaign = db.get(Campaign, draft.campaign_id)
    if campaign is not None:
        campaign_service.refresh_status(db, campaign)
    db.commit()


def resume_paused(db: Session, user: AppUser, now: datetime, settings: Settings) -> int:
    """重新連結 Outlook 後，把因權杖失效而暫停的草稿重新排程。回傳排了幾封。"""
    campaign_ids = list(
        db.scalars(
            select(EmailDraft.campaign_id)
            .join(Campaign, Campaign.campaign_id == EmailDraft.campaign_id)
            .where(
                Campaign.owner_id == user.user_id,
                EmailDraft.status == "approved",
                EmailDraft.scheduled_at.is_(None),
                EmailDraft.last_error == "MAIL_AUTH_REQUIRED",
            )
            .distinct()
        )
    )
    total = 0
    for cid in campaign_ids:
        n, _ = schedule_campaign(db, user, cid, scheduled_at=None, now=now, settings=settings)
        total += n
    return total
