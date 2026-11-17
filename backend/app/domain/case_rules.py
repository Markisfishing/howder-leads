"""案件規則：案件狀態機、回填驗證、回填帶動公司狀態、無回應判斷（F-CASE-1～3、ADR 0004）。

純 Python（CLAUDE.md 第 4 節第 2 點）。資料庫寫入在 services/case_service.py。
待辦提醒（逾期未回報、該追蹤了、無回應建議拜訪）只在 view `v_case_reminder` 定義一次（migration 0007），
這裡只放天數常數與 worker 要用的「標成無回應」判斷。
"""

from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.domain import company_rules
from app.domain.company_rules import DomainError

OVERDUE_REPORT_DAYS = 7  # 寄出 7 天沒有任何回填 → 逾期未回報
NO_RESPONSE_DAYS = 14  # 寄出 14 天還是「已寄出」→ 標成無回應，建議電話或拜訪

CASE_STATUS_LABELS = {
    "sent": "已寄出",
    "tracking": "追蹤中",
    "replied": "已回覆",
    "negotiating": "洽談中",
    "no_response": "無回應",
    "won": "成交",
    "lost": "失敗",
}
CLOSED = frozenset({"won", "lost"})

# 案件狀態 → 回填結果可以讓它變成哪些狀態。同一個狀態可以重複回填（補備註、改下次追蹤日）。
# sent 只能由系統寫（寄出信件時）。不能往回走（洽談中不能改回已回覆）。
CASE_TRANSITIONS: dict[str, frozenset[str]] = {
    "tracking": frozenset({"sent", "replied", "negotiating", "no_response", "won", "lost"}),
    "sent": frozenset({"sent", "replied", "negotiating", "no_response", "won", "lost"}),
    "no_response": frozenset({"sent", "replied", "negotiating", "no_response", "won", "lost"}),
    "replied": frozenset({"replied", "negotiating", "won", "lost"}),
    "negotiating": frozenset({"negotiating", "won", "lost"}),
    "won": frozenset(),
    "lost": frozenset(),
}

RESULT_LABELS = {
    "sent": "寄出開發信",
    "replied": "已回覆",
    "negotiating": "洽談中",
    "won": "成交",
    "lost": "失敗",
    "no_response": "無回應",
}
MANUAL_RESULTS = ("replied", "negotiating", "won", "lost", "no_response")

CHANNEL_LABELS = {
    "email": "Email",
    "line": "LINE",
    "wechat": "WeChat",
    "phone": "電話",
    "visit": "拜訪",
    "other": "其他",
    "system": "系統",
}
MANUAL_CHANNELS = ("email", "line", "wechat", "phone", "visit", "other")

# 回填結果 → 公司狀態（SPEC 3.1：sent 之後的公司狀態由案件回填帶動）
RESULT_TO_COMPANY = {"replied": "replied", "negotiating": "meeting", "won": "won", "lost": "lost"}

MAX_NOTE = 2000
MAX_AMOUNT = Decimal("999999999999")


def next_status(current: str, result: str) -> str:
    """回填結果套到案件上之後的新狀態；不合法就報錯。"""
    if current not in CASE_TRANSITIONS or result not in RESULT_LABELS:
        raise DomainError("UNKNOWN_CASE_STATUS", f"未知的案件狀態或結果：{current} → {result}", 422)
    if current in CLOSED:
        raise DomainError("CASE_CLOSED", "這件案件已經結案，不能再回填", 409)
    if result not in CASE_TRANSITIONS[current]:
        raise DomainError(
            "INVALID_CASE_RESULT",
            f"案件目前是「{CASE_STATUS_LABELS[current]}」，不能回填成「{RESULT_LABELS[result]}」",
            409,
        )
    return result


@dataclass(frozen=True)
class UpdateInput:
    channel: str
    result: str
    note: str | None
    next_follow_up: date | None
    amount_twd: Decimal | None


def validate_update(u: UpdateInput, today: date) -> UpdateInput:
    """業務人工回填的檢查。回傳整理過的內容（備註去掉頭尾空白）。"""
    if u.channel not in MANUAL_CHANNELS:
        raise DomainError("INVALID_CHANNEL", "請選擇聯絡管道", 422)
    if u.result not in MANUAL_RESULTS:
        raise DomainError("INVALID_CASE_RESULT", "請選擇回填結果", 422)
    note = (u.note or "").strip() or None
    if note and len(note) > MAX_NOTE:
        raise DomainError("NOTE_TOO_LONG", f"備註最多 {MAX_NOTE} 字", 422)
    if u.amount_twd is not None:
        if u.result != "won":
            raise DomainError("AMOUNT_ONLY_WHEN_WON", "成交金額只在結果是「成交」時填寫", 422)
        if u.amount_twd < 0 or u.amount_twd > MAX_AMOUNT:
            raise DomainError("INVALID_AMOUNT", "成交金額要是 0 以上的整數", 422)
    if u.next_follow_up is not None:
        if u.result in CLOSED:
            raise DomainError("FOLLOW_UP_ON_CLOSED", "結案的案件不需要下次追蹤日", 422)
        if u.next_follow_up < today:
            raise DomainError("FOLLOW_UP_IN_PAST", "下次追蹤日不能早於今天", 422)
    return UpdateInput(u.channel, u.result, note, u.next_follow_up, u.amount_twd)


def company_path(current: str, target: str) -> list[str]:
    """公司從 current 走到 target 要依序經過的狀態（不含 current）。走不到或已經是 target 就回傳空清單。

    例如「已寄出」直接回填成交：sent → replied → meeting → won，每一步都寫 activity_log。
    """
    if current == target:
        return []
    prev: dict[str, str] = {}
    queue = deque([current])
    while queue:
        s = queue.popleft()
        for nxt in sorted(company_rules.TRANSITIONS.get(s, frozenset())):
            # 只往「後面」走，不繞回 approved 重新開發
            if nxt in prev or nxt == current or nxt in ("approved", "drafted", "draft_approved", "rejected"):
                continue
            prev[nxt] = s
            if nxt == target:
                path = [nxt]
                while prev[path[-1]] != current:
                    path.append(prev[path[-1]])
                return path[::-1]
            queue.append(nxt)
    return []


def company_target(result: str) -> str | None:
    return RESULT_TO_COMPANY.get(result)


def needs_no_response(status: str, opened_at: datetime, now: datetime) -> bool:
    """worker 每天檢查：寄出 14 天還停在「已寄出」→ 標成無回應（F-CASE-3）。追蹤中的案件沒有寄信，不算。"""
    return status == "sent" and opened_at <= now - timedelta(days=NO_RESPONSE_DAYS)
