"""AI 寫信（M4-06c、M4-06i、M4-06j、F-MAIL-2、F-MAIL-3、ADR 0006）。

組 prompt、呼叫 LlmClient、用 domain/ai_rules 驗證回覆；JSON 不合格、混入簡體字、或暫時性的連線錯誤
會重試一次，再失敗就丟出錯誤讓草稿標成 failed（錯誤代碼給前端翻成中文）。
log 不記 prompt 或回覆內容（CLAUDE.md 第 8 節第 4 點）。
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.domain import ai_rules
from app.domain.company_rules import DomainError
from app.services.llm import LlmClient, LlmError, LlmRequest, LlmResult

PROMPT_VERSION = "invite_v1"
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
MAX_ATTEMPTS = 2  # 第一次＋重試一次

_SECTION_RE = re.compile(r"^## SYSTEM:(\w+)\s*$", re.MULTILINE)


@lru_cache
def load_system_prompt(version: str, mode: str) -> str:
    """讀 prompts/<version>.md 裡「## SYSTEM:<mode>」那一段。找不到就報錯，不默默用別的。"""
    path = PROMPTS_DIR / f"{version}.md"
    text = path.read_text(encoding="utf-8")
    matches = list(_SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        if m.group(1) == mode:
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[m.end() : end].strip()
    raise LlmError("PROMPT_NOT_FOUND")


@dataclass(frozen=True)
class Brief:
    """給 AI 的公司資料。只放公司層級的資訊；聯絡人稱呼與寄件人只在 full_ai 用來問候與署名。"""

    company_name: str
    industry: str | None = None
    product_type: str | None = None
    reason: str | None = None
    site_summary: str | None = None  # M4-08 官網摘要；沒有就留空，改靠推薦理由
    contact_name: str | None = None
    sender_name: str | None = None


def build_user_message(brief: Brief, mode: str) -> str:
    lines = [
        "【公司資料】",
        f"公司名稱：{brief.company_name}",
        f"產業：{brief.industry or '（未提供）'}",
        f"產品類型：{brief.product_type or '（未提供）'}",
        f"推薦理由：{brief.reason or '（未提供）'}",
        f"官網摘要：{brief.site_summary or '（未提供）'}",
    ]
    if mode == "full_ai":
        lines += [f"聯絡人稱呼：{brief.contact_name or '採購負責人'}", f"寄件業務：{brief.sender_name or '業務'}"]
    return "\n".join(lines)


def _attempt[T](llm: LlmClient, request: LlmRequest, parse: Callable[[str], T]) -> tuple[T, LlmResult]:
    last: Exception | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            result = llm.complete(request)
            return parse(result.text), result
        except LlmError as e:
            if not e.retryable:
                raise
            last = e
        except DomainError as e:
            if not e.code.startswith("AI_"):
                raise
            last = e
    assert last is not None
    raise last


def write_paragraph(
    llm: LlmClient, brief: Brief, *, temperature: float = 0.4
) -> tuple[ai_rules.AiParagraph, LlmResult]:
    """template_ai：只寫一段，其餘照模板。"""
    request = LlmRequest(
        system=load_system_prompt(PROMPT_VERSION, "template_ai"),
        user=build_user_message(brief, "template_ai"),
        temperature=temperature,
    )
    return _attempt(llm, request, ai_rules.parse_paragraph)


def write_mail(llm: LlmClient, brief: Brief, *, temperature: float = 0.4) -> tuple[ai_rules.AiMail, LlmResult]:
    """full_ai：主旨與整封內文（退訂說明由系統補）。"""
    request = LlmRequest(
        system=load_system_prompt(PROMPT_VERSION, "full_ai"),
        user=build_user_message(brief, "full_ai"),
        temperature=temperature,
    )
    return _attempt(llm, request, ai_rules.parse_mail)
