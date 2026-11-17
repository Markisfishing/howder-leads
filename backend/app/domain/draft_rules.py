"""草稿的狀態機、寄送檢查、改稿幅度（F-MAIL-4、F-MAIL-5、F-MAIL-8）。

純 Python（CLAUDE.md 第 4 節第 2 點）。
"""

from decimal import ROUND_HALF_UP, Decimal
from difflib import SequenceMatcher

from app.domain.company_rules import DomainError

# 草稿狀態 → 可以轉到哪些狀態。sent、discarded 是終點。
DRAFT_TRANSITIONS: dict[str, frozenset[str]] = {
    "generating": frozenset({"pending_review", "failed"}),
    "pending_review": frozenset({"approved", "discarded", "generating"}),
    # 核准後：取消核准回到待審、寄出、寄送失敗、丟棄
    "approved": frozenset({"pending_review", "sent", "failed", "discarded"}),
    # 失敗後：重新產生、修改後重新待審、丟棄
    "failed": frozenset({"generating", "pending_review", "discarded"}),
    "sent": frozenset(),
    "discarded": frozenset(),
}

DRAFT_STATUS_LABELS = {
    "generating": "產生中",
    "pending_review": "待審核",
    "approved": "已核准",
    "failed": "失敗",
    "sent": "已寄出",
    "discarded": "已丟棄",
}

# 可以修改內容的狀態（核准後要先取消核准才能改，避免改了沒人再看過就寄出）
EDITABLE = frozenset({"pending_review", "failed"})


def transition(current: str, target: str) -> str:
    if current not in DRAFT_TRANSITIONS or target not in DRAFT_TRANSITIONS:
        raise DomainError("UNKNOWN_DRAFT_STATUS", f"未知的草稿狀態：{current} → {target}", 422)
    if target not in DRAFT_TRANSITIONS[current]:
        raise DomainError(
            "INVALID_DRAFT_TRANSITION",
            f"草稿「{DRAFT_STATUS_LABELS[current]}」不能改成「{DRAFT_STATUS_LABELS[target]}」",
        )
    return target


def ensure_editable(status: str) -> None:
    if status not in EDITABLE:
        raise DomainError("DRAFT_NOT_EDITABLE", f"草稿「{DRAFT_STATUS_LABELS.get(status, status)}」不能修改", 409)


def ensure_sendable(status: str) -> None:
    """F-MAIL-5：只有已核准的草稿可以寄。寄送前在後端一定要呼叫，不能只靠前端藏按鈕。"""
    if status != "approved":
        raise DomainError("DRAFT_NOT_APPROVED", "只有已核准的草稿可以寄出", 409)


def edit_ratio(original: str | None, final: str) -> Decimal | None:
    """F-MAIL-8：業務改了原稿多少。0 = 沒改，1 = 全部重寫；沒有原稿時回傳 None。"""
    if original is None:
        return None
    a, b = " ".join(original.split()), " ".join(final.split())
    if a == b:
        return Decimal("0.000")
    similarity = SequenceMatcher(None, a, b, autojunk=False).ratio()
    value = Decimal(str(1 - similarity)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return min(max(value, Decimal("0.000")), Decimal("1.000"))
