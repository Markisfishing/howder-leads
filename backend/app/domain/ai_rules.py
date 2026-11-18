"""AI 產生內容的檢查規則（M4-06e、F-MAIL-2、F-MAIL-3、ADR 0006）。

純 Python（CLAUDE.md 第 4 節第 2 點）：不論是本機 LLM 還是 Claude，回傳的文字都先過這裡。
不合格就是這封失敗（可重新產生），不自動修補內容，避免改壞用詞。
"""

import json
import re
from dataclasses import dataclass

from app.domain.company_rules import DomainError

# 長度上限（字元）。AI 段落是插在模板中間的，不能太長
AI_PARAGRAPH_MIN = 20
AI_PARAGRAPH_MAX = 400
SUBJECT_MAX = 100
BODY_MIN = 60
BODY_MAX = 1500

# 簡體字檢查：只放「簡體專用、繁體寫法不同」的常見字（們、這、為、說、時…），
# 兩岸字形相同的字一律不放，避免誤傷。出現任何一個就視為混入簡體。
SIMPLIFIED_ONLY = frozenset(
    "们这个为说时会对发产务业应经开关东车长门问间见现电机构网优势质严测试环项让给还进过边该实员总统"
    "资证认设计达选择费价战术观压处运带单历识类体备据际将动种称联线页复买卖报导节庆乐亲爱乡书请谢话语读论谁调课谈订购贵厂创图户场满点药样专观队号"
)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass(frozen=True)
class AiParagraph:
    ai_paragraph: str


@dataclass(frozen=True)
class AiMail:
    subject: str
    body_text: str


def strip_thinking(raw: str) -> str:
    """去掉 qwen3 的 <think>…</think> 思考段（沒結尾標籤時，整段從 <think> 開始都丟掉）。"""
    text = _THINK_RE.sub("", raw)
    if "<think>" in text.lower():
        text = re.split(r"<think>", text, flags=re.IGNORECASE)[0]
    return text.strip()


def extract_json(raw: str) -> dict[str, object]:
    """從模型回覆取出 JSON 物件：容許前後有說明文字或 ``` 圍欄；取不到就報 AI_BAD_JSON。"""
    text = _FENCE_RE.sub("", strip_thinking(raw).strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise DomainError("AI_BAD_JSON", "AI 回覆不是 JSON", 422)
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise DomainError("AI_BAD_JSON", "AI 回覆的 JSON 格式錯誤", 422) from e
    if not isinstance(data, dict):
        raise DomainError("AI_BAD_JSON", "AI 回覆不是 JSON 物件", 422)
    return data


def find_simplified(text: str) -> list[str]:
    """回傳文字裡出現的簡體字（去重、照出現順序）。"""
    seen: list[str] = []
    for ch in text:
        if ch in SIMPLIFIED_ONLY and ch not in seen:
            seen.append(ch)
    return seen


def _text_field(data: dict[str, object], key: str, lo: int, hi: int, too_short: str, too_long: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DomainError("AI_MISSING_FIELD", f"AI 回覆缺少 {key}", 422)
    text = value.strip()
    if len(text) < lo:
        raise DomainError(too_short, f"AI 的 {key} 太短", 422)
    if len(text) > hi:
        raise DomainError(too_long, f"AI 的 {key} 太長", 422)
    return text


def _ensure_traditional(*texts: str) -> None:
    bad = find_simplified("".join(texts))
    if bad:
        raise DomainError("AI_SIMPLIFIED_CHINESE", f"AI 內容混入簡體字：{''.join(bad[:5])}", 422)


def parse_paragraph(raw: str) -> AiParagraph:
    """template_ai：只要 ai_paragraph 一個欄位。"""
    data = extract_json(raw)
    paragraph = _text_field(data, "ai_paragraph", AI_PARAGRAPH_MIN, AI_PARAGRAPH_MAX, "AI_TOO_SHORT", "AI_TOO_LONG")
    _ensure_traditional(paragraph)
    return AiParagraph(paragraph)


def parse_mail(raw: str) -> AiMail:
    """full_ai：主旨與整封內文（退訂說明由系統補，這裡不檢查）。"""
    data = extract_json(raw)
    subject = " ".join(_text_field(data, "subject", 1, SUBJECT_MAX, "AI_TOO_SHORT", "AI_TOO_LONG").split())
    body = _text_field(data, "body_text", BODY_MIN, BODY_MAX, "AI_TOO_SHORT", "AI_TOO_LONG")
    _ensure_traditional(subject, body)
    return AiMail(subject, body)
