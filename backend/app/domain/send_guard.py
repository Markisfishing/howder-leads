"""寄送防呆（F-MAIL-7、CLAUDE.md 第 6 節第 2 點）。

產生草稿時和真正寄出前都要呼叫（寄出前再查一次，因為中間可能有人退訂或認領）。
純 Python：資料由 services 從資料庫讀好傳進來。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from app.domain.company_rules import Ownership

RECENT_DAYS = 14


def reason_labels(recent_days: int = RECENT_DAYS) -> dict[str, str]:
    """原因代碼 → 給業務看的中文；最近寄送天數跟著設定更新。"""
    return {
        "NOT_APPROVED": "公司還沒審核通過",
        "NO_CONTACT": "沒有聯絡人",
        "CONTACT_NOT_IN_COMPANY": "聯絡人不屬於這家公司",
        "UNSUBSCRIBED": "聯絡人已退訂",
        "DO_NOT_CONTACT": "公司已設為不再聯絡",
        "LOCKED_BY_OTHER": "由其他業務負責中",
        "RECENTLY_SENT": f"{recent_days} 天內已經寄過",
        "RECIPIENT_NOT_ALLOWED": "收件者不在測試白名單（MAIL_ALLOWED_RECIPIENTS）",
    }


# 預設原因標籤，保留給純 domain 呼叫者使用。
REASON_LABELS = reason_labels()


def parse_allowlist(raw: str) -> tuple[str, ...]:
    """MAIL_ALLOWED_RECIPIENTS（逗號分隔）→ 小寫清單。完整 email，或 `@網域` 代表整個網域。"""
    return tuple(x.strip().lower() for x in raw.split(",") if x.strip())


def recipient_allowed(email: str | None, allowlist: tuple[str, ...]) -> bool:
    """真實寄信測試用的收件者白名單（M2-18）。清單是空的就不限制（正式上線）。

    `@example.com` 只比對完整網域，不比對子網域或字尾相同的網域（`@xexample.com` 不算）。
    """
    if not allowlist:
        return True
    if not email:
        return False
    addr = email.strip().lower()
    domain = addr.rpartition("@")[2]
    return any(addr == entry if not entry.startswith("@") else domain == entry[1:] for entry in allowlist)


@dataclass(frozen=True)
class GuardInput:
    company_status: str
    owner: Ownership
    contact_exists: bool
    contact_unsubscribed: bool
    last_sent_at: datetime | None  # 這家公司最近一次寄出的時間（任何業務寄的都算）
    contact_email: str | None = None  # 收件者，給白名單檢查用


def exclusions(
    g: GuardInput,
    user_id: int,
    now: datetime,
    *,
    stage: Literal["draft", "send"],
    recent_days: int = RECENT_DAYS,
    allowlist: tuple[str, ...] = (),
) -> list[str]:
    """回傳不能寄的原因代碼；空清單代表可以寄。

    stage="draft"：建立批次時，公司一定要是「已通過」。
    stage="send"：寄出前再查一次（公司那時應該是「草稿已核准」，狀態由草稿流程保證）。
    被別的業務鎖定時，主管也一樣排除：信是從寄件人本人的信箱寄出，不能替別人負責的公司寄信。
    """
    reasons: list[str] = []
    if g.company_status == "do_not_contact":
        reasons.append("DO_NOT_CONTACT")
    elif stage == "draft" and g.company_status != "approved":
        reasons.append("NOT_APPROVED")
    if not g.contact_exists:
        reasons.append("NO_CONTACT")
    elif g.contact_unsubscribed:
        reasons.append("UNSUBSCRIBED")
    if g.owner.is_locked_for(user_id, now):
        reasons.append("LOCKED_BY_OTHER")
    if g.last_sent_at is not None and g.last_sent_at > now - timedelta(days=recent_days):
        reasons.append("RECENTLY_SENT")
    if g.contact_exists and not recipient_allowed(g.contact_email, allowlist):
        reasons.append("RECIPIENT_NOT_ALLOWED")
    return reasons


def describe(reasons: list[str], recent_days: int = RECENT_DAYS) -> str:
    labels = reason_labels(recent_days)
    return "、".join(labels.get(r, r) for r in reasons)
