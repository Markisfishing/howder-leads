"""AI 內容檢查規則（M4-06e、F-MAIL-3）。全是純函式，不連任何 LLM。"""

import pytest

from app.domain import ai_rules
from app.domain.company_rules import DomainError

GOOD_PARAGRAPH = "我們注意到貴公司在工業自動化領域的控制箱與配電設備需求，厚達電子專注於端子台製造，期待有機會交流。"
GOOD_BODY = (
    "您好，我們是厚達電子，專注於端子台的設計與製造。看到貴公司的產品包含控制箱與配電設備，"
    "想與您聊聊是否有合作的機會。若方便，歡迎回信告知適合的聯絡時間。"
)


def test_m4_06e_strip_thinking_removes_closed_block() -> None:
    assert ai_rules.strip_thinking('<think>先想一下\n再想</think>\n{"a": 1}') == '{"a": 1}'


def test_m4_06e_strip_thinking_drops_unclosed_block() -> None:
    assert ai_rules.strip_thinking('{"a": 1}<think>想到一半被截斷') == '{"a": 1}'


@pytest.mark.parametrize(
    "raw",
    [
        '{"ai_paragraph": "x"}',
        '好的，以下是結果：\n{"ai_paragraph": "x"}\n希望有幫助',
        '```json\n{"ai_paragraph": "x"}\n```',
        '<think>…</think>{"ai_paragraph": "x"}',
    ],
)
def test_m4_06e_extract_json_tolerates_wrappers(raw: str) -> None:
    assert ai_rules.extract_json(raw) == {"ai_paragraph": "x"}


@pytest.mark.parametrize("raw", ["", "沒有 JSON", "{壞掉的 json", "[1, 2]"])
def test_m4_06e_extract_json_rejects_bad(raw: str) -> None:
    with pytest.raises(DomainError) as e:
        ai_rules.extract_json(raw)
    assert e.value.code == "AI_BAD_JSON"


def test_m4_06e_parse_paragraph_ok() -> None:
    assert ai_rules.parse_paragraph(f'{{"ai_paragraph": "{GOOD_PARAGRAPH}"}}').ai_paragraph == GOOD_PARAGRAPH


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ('{"other": "x"}', "AI_MISSING_FIELD"),
        ('{"ai_paragraph": ""}', "AI_MISSING_FIELD"),
        ('{"ai_paragraph": 5}', "AI_MISSING_FIELD"),
        ('{"ai_paragraph": "太短"}', "AI_TOO_SHORT"),
        ('{"ai_paragraph": "' + "字" * 401 + '"}', "AI_TOO_LONG"),
    ],
)
def test_m4_06e_parse_paragraph_rejects(raw: str, code: str) -> None:
    with pytest.raises(DomainError) as e:
        ai_rules.parse_paragraph(raw)
    assert e.value.code == code


def test_m4_06e_parse_mail_ok_and_collapses_subject_whitespace() -> None:
    raw = '{"subject": "合作  邀請\\n厚達電子", "body_text": "' + GOOD_BODY + '"}'
    mail = ai_rules.parse_mail(raw)
    assert mail.subject == "合作 邀請 厚達電子"
    assert mail.body_text == GOOD_BODY


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (f'{{"body_text": "{GOOD_BODY}"}}', "AI_MISSING_FIELD"),
        ('{"subject": "好", "body_text": "太短"}', "AI_TOO_SHORT"),
        (f'{{"subject": "{"字" * 101}", "body_text": "{GOOD_BODY}"}}', "AI_TOO_LONG"),
        ('{"subject": "好", "body_text": "' + "字" * 1501 + '"}', "AI_TOO_LONG"),
    ],
)
def test_m4_06e_parse_mail_rejects(raw: str, code: str) -> None:
    with pytest.raises(DomainError) as e:
        ai_rules.parse_mail(raw)
    assert e.value.code == code


def test_m4_06e_simplified_chinese_rejected_in_paragraph_and_mail() -> None:
    simplified = "我们注意到贵公司在工业自动化领域的需求，厚达电子专注于端子台制造，期待有机会交流与合作。"
    with pytest.raises(DomainError) as e:
        ai_rules.parse_paragraph(f'{{"ai_paragraph": "{simplified}"}}')
    assert e.value.code == "AI_SIMPLIFIED_CHINESE"
    with pytest.raises(DomainError) as e2:
        ai_rules.parse_mail(f'{{"subject": "合作邀请", "body_text": "{GOOD_BODY}"}}')
    assert e2.value.code == "AI_SIMPLIFIED_CHINESE"


def test_m4_06e_find_simplified_does_not_flag_common_traditional_text() -> None:
    traditional = (
        "您好，我們是厚達電子，專注於端子台製造。為了與貴公司開發合作，經過評估，"
        "請問是否方便聯絡？電機控制、連接器、網路設備。"
    )
    assert ai_rules.find_simplified(traditional) == []
    assert ai_rules.find_simplified("们这为说") == ["们", "这", "为", "说"]
