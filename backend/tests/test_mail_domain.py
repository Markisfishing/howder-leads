"""寄信相關的 domain 規則（M2-04a、M2-06a、M2-07d、M2-08a）。純函式，不碰資料庫。"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.domain import draft_rules, send_limits
from app.domain.company_rules import DomainError, Ownership
from app.domain.send_guard import GuardInput, describe, exclusions, parse_allowlist, recipient_allowed

NOW = datetime(2026, 11, 17, 2, 0, tzinfo=UTC)  # 台灣時間 10:00
ME, OTHER = 1, 2


def _g(**kw: object) -> GuardInput:
    base: dict[str, object] = {
        "company_status": "approved",
        "owner": Ownership(None, None),
        "contact_exists": True,
        "contact_unsubscribed": False,
        "last_sent_at": None,
    }
    base.update(kw)
    return GuardInput(**base)  # type: ignore[arg-type]


# ---------- 寄送防呆（F-MAIL-7）----------
def test_f_mail_7_clean_target_passes() -> None:
    assert exclusions(_g(), ME, NOW, stage="draft") == []


def test_f_mail_7_unsubscribed_contact() -> None:
    assert exclusions(_g(contact_unsubscribed=True), ME, NOW, stage="draft") == ["UNSUBSCRIBED"]


def test_f_mail_7_do_not_contact_company() -> None:
    assert exclusions(_g(company_status="do_not_contact"), ME, NOW, stage="send") == ["DO_NOT_CONTACT"]


def test_f_mail_7_locked_by_other_even_for_manager() -> None:
    locked = Ownership(OTHER, NOW + timedelta(days=5))
    assert exclusions(_g(owner=locked), ME, NOW, stage="draft") == ["LOCKED_BY_OTHER"]
    # 自己負責或鎖定已過期都可以
    assert exclusions(_g(owner=Ownership(ME, NOW + timedelta(days=5))), ME, NOW, stage="draft") == []
    assert exclusions(_g(owner=Ownership(OTHER, NOW - timedelta(days=1))), ME, NOW, stage="draft") == []


def test_f_mail_7_recently_sent_within_14_days() -> None:
    assert exclusions(_g(last_sent_at=NOW - timedelta(days=13)), ME, NOW, stage="draft") == ["RECENTLY_SENT"]
    assert exclusions(_g(last_sent_at=NOW - timedelta(days=15)), ME, NOW, stage="draft") == []


def test_f_mail_7_no_contact() -> None:
    assert exclusions(_g(contact_exists=False), ME, NOW, stage="draft") == ["NO_CONTACT"]


def test_f_mail_7_draft_stage_requires_approved_company() -> None:
    assert exclusions(_g(company_status="pending_review"), ME, NOW, stage="draft") == ["NOT_APPROVED"]
    # 寄出階段公司是「草稿已核准」，不檢查 approved
    assert exclusions(_g(company_status="draft_approved"), ME, NOW, stage="send") == []


def test_f_mail_7_multiple_reasons_and_description() -> None:
    reasons = exclusions(
        _g(contact_unsubscribed=True, last_sent_at=NOW, owner=Ownership(OTHER, NOW + timedelta(days=1))),
        ME,
        NOW,
        stage="draft",
    )
    assert reasons == ["UNSUBSCRIBED", "LOCKED_BY_OTHER", "RECENTLY_SENT"]
    assert describe(reasons) == "聯絡人已退訂、由其他業務負責中、14 天內已經寄過"


# ---------- 測試收件者白名單（M2-18）----------
def test_m2_18_parse_allowlist() -> None:
    assert parse_allowlist(" Test1@Example.com, @Corp.example.com ,,") == ("test1@example.com", "@corp.example.com")
    assert parse_allowlist("") == ()


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("test1@example.com", True),
        ("TEST1@example.com ", True),
        ("test2@example.com", False),
        ("anyone@corp.example.com", True),
        ("x@sub.corp.example.com", False),  # 子網域不算
        ("x@xcorp.example.com", False),  # 字尾相同的網域不算
        (None, False),
    ],
)
def test_m2_18_recipient_allowed(email: str | None, expected: bool) -> None:
    allow = ("test1@example.com", "@corp.example.com")
    assert recipient_allowed(email, allow) is expected


def test_m2_18_empty_allowlist_allows_everyone() -> None:
    assert recipient_allowed("buyer@example.com", ()) is True
    assert exclusions(_g(contact_email="buyer@example.com"), ME, NOW, stage="send") == []


def test_m2_18_guard_blocks_recipient_outside_allowlist() -> None:
    allow = ("test1@example.com",)
    g = _g(contact_email="buyer@example.com")
    assert exclusions(g, ME, NOW, stage="draft", allowlist=allow) == ["RECIPIENT_NOT_ALLOWED"]
    assert exclusions(g, ME, NOW, stage="send", allowlist=allow) == ["RECIPIENT_NOT_ALLOWED"]
    assert exclusions(_g(contact_email="test1@example.com"), ME, NOW, stage="send", allowlist=allow) == []
    # 沒有聯絡人時只報「沒有聯絡人」，不重複報白名單
    assert exclusions(_g(contact_exists=False), ME, NOW, stage="send", allowlist=allow) == ["NO_CONTACT"]
    assert describe(["RECIPIENT_NOT_ALLOWED"]) == "收件者不在測試白名單（MAIL_ALLOWED_RECIPIENTS）"


# ---------- 草稿狀態機 ----------
@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("generating", "pending_review"),
        ("generating", "failed"),
        ("pending_review", "approved"),
        ("pending_review", "discarded"),
        ("approved", "pending_review"),
        ("approved", "sent"),
        ("failed", "generating"),
    ],
)
def test_m2_05a_legal_draft_transitions(current: str, target: str) -> None:
    assert draft_rules.transition(current, target) == target


@pytest.mark.parametrize(
    ("current", "target"),
    [("generating", "approved"), ("pending_review", "sent"), ("sent", "pending_review"), ("discarded", "approved")],
)
def test_m2_05a_illegal_draft_transitions(current: str, target: str) -> None:
    with pytest.raises(DomainError) as e:
        draft_rules.transition(current, target)
    assert e.value.code == "INVALID_DRAFT_TRANSITION"


def test_m2_05a_only_pending_or_failed_is_editable() -> None:
    draft_rules.ensure_editable("pending_review")
    draft_rules.ensure_editable("failed")
    with pytest.raises(DomainError) as e:
        draft_rules.ensure_editable("approved")
    assert e.value.code == "DRAFT_NOT_EDITABLE"


# ---------- 只有核准的才寄（F-MAIL-5）----------
@pytest.mark.parametrize("status", ["generating", "pending_review", "discarded", "sent", "failed"])
def test_f_mail_5_non_approved_draft_cannot_be_sent(status: str) -> None:
    with pytest.raises(DomainError) as e:
        draft_rules.ensure_sendable(status)
    assert e.value.code == "DRAFT_NOT_APPROVED"


def test_f_mail_5_approved_draft_can_be_sent() -> None:
    draft_rules.ensure_sendable("approved")


# ---------- 改稿幅度（F-MAIL-8）----------
def test_f_mail_8_edit_ratio() -> None:
    assert draft_rules.edit_ratio("原稿內容", "原稿內容") == Decimal("0.000")
    assert draft_rules.edit_ratio("原稿 內容", "原稿\n內容") == Decimal("0.000")  # 只差空白不算改
    assert draft_rules.edit_ratio("abc", "xyz") == Decimal("1.000")
    partial = draft_rules.edit_ratio("您好，我是厚達電子的業務。", "您好，我是厚達電子業務部的小陳。")
    assert partial is not None and Decimal("0") < partial < Decimal("1")
    assert draft_rules.edit_ratio(None, "x") is None


# ---------- 寄送排程（F-MAIL-6）----------
def test_f_mail_6_paces_per_minute() -> None:
    times = send_limits.plan_send_times(3, start=NOW, already_today=0, daily_limit=50, per_minute=2)
    assert times == [NOW, NOW + timedelta(seconds=30), NOW + timedelta(seconds=60)]


def test_f_mail_6_daily_limit_moves_rest_to_next_morning() -> None:
    times = send_limits.plan_send_times(4, start=NOW, already_today=48, daily_limit=50, per_minute=60)
    assert times[:2] == [NOW, NOW + timedelta(seconds=1)]
    next_morning = datetime(2026, 11, 18, 1, 0, tzinfo=UTC)  # 台灣 11/18 09:00
    assert times[2] == next_morning
    assert times[3] == next_morning + timedelta(seconds=1)


def test_f_mail_6_already_at_limit_starts_tomorrow() -> None:
    times = send_limits.plan_send_times(1, start=NOW, already_today=50, daily_limit=50, per_minute=10)
    assert send_limits.local_day(times[0]).isoformat() == "2026-11-18"


def test_f_mail_6_day_is_taiwan_time() -> None:
    late = datetime(2026, 11, 17, 15, 59, tzinfo=UTC)  # 台灣 23:59
    assert send_limits.local_day(late).isoformat() == "2026-11-17"
    assert send_limits.local_day(late + timedelta(minutes=2)).isoformat() == "2026-11-18"
