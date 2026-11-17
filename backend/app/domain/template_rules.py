"""郵件模板：變數白名單、退訂說明、渲染（M2-02a、M2-03a）。

純 Python（CLAUDE.md 第 4 節第 2 點）。模板和草稿都是業務編輯的純文字，
這裡負責代入變數，再轉成只有 <p>、<br> 的 HTML；使用者輸入一律跳脫，不會變成 HTML 標籤。
"""

import html
import re
from collections.abc import Mapping

from app.domain.company_rules import DomainError

# 變數白名單（SPEC F-MAIL-2）。值由 services 從資料庫組好傳進來。
VARIABLES: dict[str, str] = {
    "company_name": "公司名稱",
    "contact_name": "聯絡人稱呼",
    "contact_title": "聯絡人職稱",
    "industry": "產業",
    "sender_name": "寄件業務姓名",
    "sender_email": "寄件業務 email",
    "ai_paragraph": "AI 段落（M4 開放；只用模板時是空的）",
    "unsubscribe": "退訂說明（必填，系統自動代入固定文字）",
}
# 這些變數可以是空的：沒有值時整行拿掉
OPTIONAL = frozenset({"ai_paragraph", "contact_title"})

# 退訂說明（SPEC 7.5：每封信的結尾都要有）。正式文字等 SPEC 11-5，先用這段。
UNSUBSCRIBE_TEXT = "如果您不希望再收到厚達電子的來信，請直接回覆「不需要」，我們會立即停止寄送。"

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
SUBJECT_MAX = 200
BODY_MAX = 20000


def variables_in(text: str) -> list[str]:
    return [m.group(1) for m in _VAR_RE.finditer(text)]


def validate_template(subject: str, body_text: str) -> None:
    """存檔前檢查：主旨與內文不能空、只能用白名單變數、內文一定要有 {{unsubscribe}}。"""
    if not subject.strip():
        raise DomainError("TEMPLATE_SUBJECT_REQUIRED", "主旨不能空白", 422)
    if not body_text.strip():
        raise DomainError("TEMPLATE_BODY_REQUIRED", "內文不能空白", 422)
    if len(subject) > SUBJECT_MAX or len(body_text) > BODY_MAX:
        raise DomainError("TEMPLATE_TOO_LONG", "主旨或內文太長", 422)
    if "\n" in subject:
        raise DomainError("TEMPLATE_SUBJECT_MULTILINE", "主旨只能一行", 422)
    unknown = sorted({v for v in variables_in(subject) + variables_in(body_text) if v not in VARIABLES})
    if unknown:
        raise DomainError("TEMPLATE_UNKNOWN_VARIABLE", f"不認得的變數：{'、'.join(unknown)}", 422)
    if "unsubscribe" in variables_in(subject):
        raise DomainError("TEMPLATE_UNSUBSCRIBE_IN_SUBJECT", "退訂說明要放在內文，不能放在主旨", 422)
    if "unsubscribe" not in variables_in(body_text):
        raise DomainError("TEMPLATE_MISSING_UNSUBSCRIBE", "內文一定要有 {{unsubscribe}} 退訂說明", 422)


def _substitute(text: str, values: Mapping[str, str | None], *, drop_empty_lines: bool) -> str:
    missing = sorted(
        {
            v
            for v in variables_in(text)
            if v not in OPTIONAL and v != "unsubscribe" and not (values.get(v) or "").strip()
        }
    )
    if missing:
        names = "、".join(VARIABLES.get(v, v) for v in missing)
        raise DomainError("TEMPLATE_MISSING_VALUE", f"缺少資料：{names}", 422)

    def repl(m: re.Match[str]) -> str:
        name = m.group(1)
        if name == "unsubscribe":
            return UNSUBSCRIBE_TEXT
        return (values.get(name) or "").strip()

    if not drop_empty_lines:
        return _VAR_RE.sub(repl, text)
    lines = []
    for line in text.split("\n"):
        rendered = _VAR_RE.sub(repl, line)
        # 這一行只有選填變數、而且沒有值 → 整行拿掉，避免留下空段落
        if variables_in(line) and not rendered.strip() and line.strip():
            continue
        lines.append(rendered)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def ensure_unsubscribe(body_text: str) -> str:
    """強制附上退訂說明：內文裡沒有就加在最後（業務改稿時刪掉也會補回來）。"""
    if UNSUBSCRIBE_TEXT in body_text:
        return body_text
    return body_text.rstrip() + "\n\n" + UNSUBSCRIBE_TEXT


def render(subject: str, body_text: str, values: Mapping[str, str | None]) -> tuple[str, str]:
    """代入變數，回傳 (主旨, 純文字內文)。缺必要變數就報錯；一定附上退訂說明。"""
    for v in variables_in(subject) + variables_in(body_text):
        if v not in VARIABLES:
            raise DomainError("TEMPLATE_UNKNOWN_VARIABLE", f"不認得的變數：{v}", 422)
    out_subject = " ".join(_substitute(subject, values, drop_empty_lines=False).split())
    out_body = ensure_unsubscribe(_substitute(body_text, values, drop_empty_lines=True))
    return out_subject, out_body


def text_to_html(body_text: str) -> str:
    """純文字 → HTML：先跳脫，再把空行分段成 <p>、單一換行變 <br>。"""
    paragraphs = [p for p in re.split(r"\n\s*\n", body_text.replace("\r\n", "\n").strip()) if p.strip()]
    return "".join("<p>" + html.escape(p.strip()).replace("\n", "<br>") + "</p>" for p in paragraphs)
