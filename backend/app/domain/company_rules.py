"""公司的商業規則：狀態機、審核、認領鎖定（SPEC 3.1）。

這個模組是純 Python：不 import FastAPI、SQLAlchemy 或外部 SDK（CLAUDE.md 第 4 節第 2 點），
所以每條規則都可以直接寫單元測試。資料庫寫入與 activity_log 由 services/company_service.py 負責。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta


class DomainError(Exception):
    """違反商業規則。code 給前端對應中文訊息，status 是建議的 HTTP 狀態碼。"""

    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


# ---------- 狀態機 ----------
# 每個狀態可以轉到哪些狀態。do_not_contact、won 是終點。
TRANSITIONS: dict[str, frozenset[str]] = {
    "imported": frozenset({"pending_review"}),
    "pending_review": frozenset({"approved", "rejected"}),
    # 「加入追蹤」（F-REC-9）的公司沒有寄信，由案件回填直接改成已回覆或失敗（M3-08a）
    "approved": frozenset({"rejected", "drafted", "replied", "lost"}),
    "rejected": frozenset({"approved"}),  # 重新審核
    "drafted": frozenset({"draft_approved", "approved"}),  # 草稿丟棄就回到 approved
    "draft_approved": frozenset({"sent", "drafted"}),
    "sent": frozenset({"replied", "lost"}),
    "replied": frozenset({"meeting", "lost"}),
    "meeting": frozenset({"won", "lost"}),
    "lost": frozenset({"approved"}),  # 之後可以重新開發
    "won": frozenset(),
    "do_not_contact": frozenset(),
}
# 退信／退訂：除了終點以外，任何狀態都可以直接轉成 do_not_contact
_ANY_TO_DNC = frozenset(TRANSITIONS) - {"won", "do_not_contact"}

STATUS_LABELS = {
    "imported": "已匯入",
    "pending_review": "待審",
    "approved": "已通過",
    "rejected": "已排除",
    "drafted": "草稿已產生",
    "draft_approved": "草稿已核准",
    "sent": "已寄出",
    "replied": "已回覆",
    "meeting": "會議",
    "won": "成交",
    "lost": "失敗",
    "do_not_contact": "不再聯絡",
}


def can_transition(current: str, target: str) -> bool:
    if target == "do_not_contact":
        return current in _ANY_TO_DNC
    return target in TRANSITIONS.get(current, frozenset())


def transition(current: str, target: str) -> str:
    if current not in TRANSITIONS or target not in TRANSITIONS:
        raise DomainError("UNKNOWN_STATUS", f"未知的狀態：{current} → {target}", 422)
    if not can_transition(current, target):
        raise DomainError(
            "INVALID_TRANSITION",
            f"狀態「{STATUS_LABELS[current]}」不能改成「{STATUS_LABELS[target]}」",
        )
    return target


def status_after_resubscribe(current: str) -> str | None:
    """M3-18：主管取消聯絡人退訂後，公司的狀態怎麼退回。

    - 「不再聯絡」是狀態機的終點，一般轉換出不去；只有取消退訂可以回到「已通過」，
      重新進入候選名單（先前的寄信／回覆進度不帶回來，要重新產生草稿、重新寄）。
    - 其他狀態（進行中、成交…）公司本來就可以聯絡，不改。
    """
    return "approved" if current == "do_not_contact" else None


# ---------- 審核 ----------
REJECT_REASONS = (
    "wrong_industry",
    "existing_customer",
    "competitor",
    "wrong_website",
    "no_demand",
    "closed_business",
    "other",
)


def review_target(decision: str, reject_reason: str | None) -> str:
    """驗證審核內容，回傳要轉成的狀態。排除一定要有原因（SPEC 3.1）。"""
    if decision == "approved":
        if reject_reason:
            raise DomainError("REASON_NOT_ALLOWED", "通過時不需要排除原因", 422)
        return "approved"
    if decision == "rejected":
        if not reject_reason:
            raise DomainError("REJECT_REASON_REQUIRED", "排除時一定要選原因", 422)
        if reject_reason not in REJECT_REASONS:
            raise DomainError("UNKNOWN_REJECT_REASON", f"未知的排除原因：{reject_reason}", 422)
        return "rejected"
    raise DomainError("UNKNOWN_DECISION", f"未知的審核結果：{decision}", 422)


# ---------- 認領與鎖定 ----------
@dataclass(frozen=True)
class Ownership:
    owner_id: int | None
    locked_until: datetime | None

    def is_locked_for(self, user_id: int, now: datetime) -> bool:
        """這家公司是否被「別人」鎖定中。"""
        return (
            self.owner_id is not None
            and self.owner_id != user_id
            and self.locked_until is not None
            and self.locked_until > now
        )


def claim(current: Ownership, user_id: int, now: datetime, lock_days: int) -> Ownership:
    """認領：沒有人負責、自己負責、或別人的鎖定已過期時才能認領。自己再認領一次會延長鎖定。"""
    if current.is_locked_for(user_id, now):
        assert current.locked_until is not None
        raise DomainError("COMPANY_LOCKED", f"這家公司由其他業務負責，鎖定到 {current.locked_until:%Y-%m-%d}")
    return Ownership(owner_id=user_id, locked_until=now + timedelta(days=lock_days))


def release(current: Ownership, user_id: int, is_manager: bool) -> Ownership:
    """釋出：只有負責人本人或主管可以。"""
    if current.owner_id is None:
        return current
    if current.owner_id != user_id and not is_manager:
        raise DomainError("NOT_OWNER", "只有負責業務或主管可以釋出這家公司", 403)
    return Ownership(owner_id=None, locked_until=None)


def assign(target_user_id: int, now: datetime, lock_days: int, is_manager: bool) -> Ownership:
    """主管重新分派（SPEC 第 2 節）：不管目前鎖定，直接交給指定業務。"""
    if not is_manager:
        raise DomainError("FORBIDDEN", "只有主管可以重新分派", 403)
    return Ownership(owner_id=target_user_id, locked_until=now + timedelta(days=lock_days))


def ensure_can_act(current: Ownership, user_id: int, now: datetime, is_manager: bool) -> None:
    """審核、修正資料前檢查：被別的業務鎖定中的公司，只有主管可以動。"""
    if current.is_locked_for(user_id, now) and not is_manager:
        raise DomainError("COMPANY_LOCKED", "這家公司由其他業務負責，不能修改")
