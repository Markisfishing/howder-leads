"""聯絡人的商業規則（M2-01a，SPEC 9 個資）。

純 Python：不 import FastAPI、SQLAlchemy（CLAUDE.md 第 4 節第 2 點）。
"""

import re

from app.domain.company_rules import DomainError

# 聯絡人來源，和 migration 0004 的 ck_contact_source 一致
CONTACT_SOURCES = ("website", "business_card", "referral", "exhibition", "manual")

# 只擋明顯打錯的格式（一個 @、網域有點、沒有空白），真正能不能收信要靠退信判斷
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s.]+$")
_EMAIL_MAX = 254


def normalize_email(raw: str) -> str:
    """去掉前後空白、轉小寫並檢查格式；同一家公司不重複就是比這個值。"""
    email = raw.strip().lower()
    if not email or len(email) > _EMAIL_MAX or not _EMAIL_RE.match(email) or ".." in email:
        raise DomainError("INVALID_EMAIL", "email 格式不正確", 422)
    return email


def check_source(source: str) -> str:
    if source not in CONTACT_SOURCES:
        raise DomainError("INVALID_SOURCE", "請選擇聯絡人來源", 422)
    return source


def company_stops_contact(*, whole_company: bool, reachable_left: int) -> bool:
    """F-CASE-5（2026-11-18 改）：退訂只標記那位聯絡人；公司什麼時候才改成「不再聯絡」。

    - 客戶明講整家公司都不要聯絡（whole_company）→ 是
    - 公司已沒有其他可聯絡（沒退訂）的聯絡人 → 是
    - 否則公司照常，其他聯絡人還可以寄
    """
    if reachable_left < 0:
        raise ValueError("reachable_left 不能是負數")
    return whole_company or reachable_left == 0


def check_delete_reason(reason: str | None) -> str:
    """個資刪除一定要寫原因（例如客戶來信要求），留在 activity_log 備查。"""
    text = (reason or "").strip()
    if not text:
        raise DomainError("DELETE_REASON_REQUIRED", "刪除個資要填寫原因", 422)
    return text


def check_resubscribe_reason(reason: str | None) -> str:
    """M3-18 取消退訂一定要寫原因（例如客戶來信同意恢復聯絡），留在 activity_log 備查。"""
    text = (reason or "").strip()
    if not text:
        raise DomainError("RESUBSCRIBE_REASON_REQUIRED", "取消退訂要填寫原因", 422)
    return text
