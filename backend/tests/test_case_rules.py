"""案件 domain 規則（M3-08a、F-CASE-2、F-CASE-3）。"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.domain import case_rules as rules
from app.domain import company_rules
from app.domain.company_rules import DomainError

TODAY = date(2026, 11, 18)
NOW = datetime(2026, 11, 18, 3, 0, tzinfo=UTC)


def _u(**kw: object) -> rules.UpdateInput:
    base: dict[str, object] = {
        "channel": "phone",
        "result": "replied",
        "note": None,
        "next_follow_up": None,
        "amount_twd": None,
    }
    return rules.UpdateInput(**{**base, **kw})  # type: ignore[arg-type]


# ---------- 狀態機 ----------
@pytest.mark.parametrize(
    ("current", "result"),
    [
        ("sent", "replied"),
        ("sent", "won"),  # 可以跳級
        ("tracking", "negotiating"),
        ("replied", "replied"),  # 同一個狀態可以重複回填
        ("negotiating", "lost"),
        ("no_response", "replied"),  # 無回應之後客戶又回了
        ("no_response", "sent"),  # 再寄一封
    ],
)
def test_f_case_2_legal_results(current: str, result: str) -> None:
    assert rules.next_status(current, result) == result


@pytest.mark.parametrize(("current", "result"), [("negotiating", "replied"), ("replied", "no_response")])
def test_f_case_2_cannot_go_backwards(current: str, result: str) -> None:
    with pytest.raises(DomainError) as e:
        rules.next_status(current, result)
    assert e.value.code == "INVALID_CASE_RESULT"


@pytest.mark.parametrize("closed", ["won", "lost"])
def test_f_case_2_closed_case_cannot_update(closed: str) -> None:
    with pytest.raises(DomainError) as e:
        rules.next_status(closed, "replied")
    assert e.value.code == "CASE_CLOSED"


def test_every_case_status_has_label() -> None:
    assert set(rules.CASE_STATUS_LABELS) == set(rules.CASE_TRANSITIONS)


# ---------- 回填驗證 ----------
def test_f_case_2_valid_update_strips_note() -> None:
    out = rules.validate_update(_u(note="  客戶說下週回覆  ", next_follow_up=TODAY), TODAY)
    assert out.note == "客戶說下週回覆"


@pytest.mark.parametrize(
    ("kw", "code"),
    [
        ({"channel": "system"}, "INVALID_CHANNEL"),  # 系統事件不能手動回填
        ({"result": "sent"}, "INVALID_CASE_RESULT"),
        ({"amount_twd": Decimal(1000)}, "AMOUNT_ONLY_WHEN_WON"),
        ({"result": "won", "amount_twd": Decimal(-1)}, "INVALID_AMOUNT"),
        ({"next_follow_up": TODAY - timedelta(days=1)}, "FOLLOW_UP_IN_PAST"),
        ({"result": "lost", "next_follow_up": TODAY}, "FOLLOW_UP_ON_CLOSED"),
        ({"note": "字" * 2001}, "NOTE_TOO_LONG"),
    ],
)
def test_f_case_2_invalid_updates(kw: dict[str, object], code: str) -> None:
    with pytest.raises(DomainError) as e:
        rules.validate_update(_u(**kw), TODAY)
    assert e.value.code == code


def test_f_case_2_won_with_amount() -> None:
    assert rules.validate_update(_u(result="won", amount_twd=Decimal(50000)), TODAY).amount_twd == 50000


# ---------- 帶動公司狀態 ----------
@pytest.mark.parametrize(
    ("current", "result", "path"),
    [
        ("sent", "replied", ["replied"]),
        ("sent", "won", ["replied", "meeting", "won"]),  # 跳級時依序走過中間狀態
        ("sent", "negotiating", ["replied", "meeting"]),
        ("replied", "lost", ["lost"]),
        ("approved", "replied", ["replied"]),  # 加入追蹤的公司
        ("approved", "won", ["replied", "meeting", "won"]),
        ("meeting", "replied", []),  # 公司已經在更後面，不倒退
        ("do_not_contact", "won", []),  # 不再聯絡是終點
        ("sent", "no_response", []),  # 無回應不改公司狀態
    ],
)
def test_f_case_2_company_follows_case(current: str, result: str, path: list[str]) -> None:
    target = rules.company_target(result)
    got = rules.company_path(current, target) if target else []
    assert got == path
    for a, b in zip([current, *got], got, strict=False):
        assert company_rules.can_transition(a, b)


# ---------- 無回應 ----------
def test_f_case_3_mark_no_response_after_14_days() -> None:
    assert rules.needs_no_response("sent", NOW - timedelta(days=14), NOW)
    assert not rules.needs_no_response("sent", NOW - timedelta(days=13, hours=23), NOW)
    assert not rules.needs_no_response("replied", NOW - timedelta(days=30), NOW)
    assert not rules.needs_no_response("tracking", NOW - timedelta(days=30), NOW)  # 沒寄信不算
