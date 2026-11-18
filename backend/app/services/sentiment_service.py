"""回覆態度（M4-07b、M4-07c、F-TRK-2）。

回填有備註時排 classify_reply 工作，由本機 LLM 判斷客戶態度；判斷失敗不影響回填本身（sentiment 留空）。
業務手動修正的值（source = manual）永遠優先，AI 後到也不會覆蓋。
log 與 activity_log 只記編號與態度代碼，不記備註內容（CLAUDE.md 第 8 節第 4 點）。
"""

from sqlalchemy.orm import Session

from app.domain import ai_rules
from app.domain.company_rules import DomainError
from app.models import AppUser, CaseUpdate
from app.services import ai_writer, jobs
from app.services import company_service as company_svc
from app.services.llm import LlmClient, LlmError, LlmRequest

KIND = "classify_reply"
PROMPT_VERSION = "reply_sentiment_v1"


def should_classify(channel: str, note: str | None) -> bool:
    """人工回填、而且有備註才判斷；系統事件與沒備註的回填沒有可判斷的內容。"""
    return channel != "system" and bool(note and note.strip())


def enqueue(db: Session, update: CaseUpdate, user_id: int | None) -> None:
    """排進佇列（不 commit，和回填一起 commit）。只做一次重試：態度只是輔助資訊。"""
    if should_classify(update.channel, update.note):
        jobs.enqueue(db, KIND, {"update_id": update.update_id}, created_by=user_id, max_attempts=2)


def classify_update(db: Session, update_id: int, llm: LlmClient) -> None:
    """worker handler：判斷一筆回填的態度。失敗丟 JobError（讓佇列決定要不要重試）。"""
    update = db.get(CaseUpdate, update_id)
    if update is None or update.sentiment_source == "manual" or not should_classify(update.channel, update.note):
        return
    request = LlmRequest(
        system=ai_writer.load_system_prompt(PROMPT_VERSION, "sentiment"),
        user=f"【客戶回覆備註】\n{(update.note or '').strip()}",
        temperature=0.0,
    )
    try:
        result = llm.complete(request)
        sentiment = ai_rules.parse_sentiment(result.text)
    except LlmError as e:
        raise jobs.JobError(e.code, retryable=e.retryable) from e
    except DomainError as e:
        raise jobs.JobError(e.code, retryable=True) from e
    db.refresh(update)  # 等待 LLM 期間業務可能已經手動修正
    if update.sentiment_source == "manual":
        return
    update.sentiment, update.sentiment_source = sentiment, "ai"
    db.commit()


def set_manual(db: Session, user: AppUser, update: CaseUpdate, sentiment: str, company_id: int) -> CaseUpdate:
    """業務手動修正態度，並寫 activity_log（只記編號與態度代碼）。"""
    value = ai_rules.check_sentiment(sentiment)
    old = update.sentiment
    update.sentiment, update.sentiment_source = value, "manual"
    company_svc.log(
        db,
        company_svc.get_company(db, company_id),
        user,
        "case_sentiment",
        from_value=old,
        to_value=value,
        note=f"update:{update.update_id}",
    )
    db.commit()
    return update
