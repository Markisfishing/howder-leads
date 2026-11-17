"""公司商業規則的單元測試（M1-23、M1-26、SPEC 3.1）。純 Python，不需要資料庫。"""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain import company_rules as rules
from app.domain.company_rules import DomainError, Ownership

NOW = datetime(2026, 11, 17, 9, 0, tzinfo=UTC)


# ---------- 狀態機 ----------
@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("imported", "pending_review"),
        ("pending_review", "approved"),
        ("pending_review", "rejected"),
        ("approved", "rejected"),
        ("rejected", "approved"),
        ("approved", "drafted"),
        ("drafted", "draft_approved"),
        ("draft_approved", "sent"),
        ("sent", "replied"),
        ("replied", "meeting"),
        ("meeting", "won"),
        ("meeting", "lost"),
        ("sent", "do_not_contact"),
        ("pending_review", "do_not_contact"),
    ],
)
def test_m1_23_legal_transitions(current: str, target: str) -> None:
    assert rules.transition(current, target) == target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("pending_review", "sent"),  # 不能跳過審核和核准
        ("approved", "sent"),  # 沒有核准的草稿不能寄（F-MAIL-5 的狀態面）
        ("rejected", "drafted"),
        ("approved", "approved"),
        ("won", "lost"),
        ("do_not_contact", "approved"),  # 不再聯絡是終點
        ("won", "do_not_contact"),
    ],
)
def test_m1_23_illegal_transitions(current: str, target: str) -> None:
    with pytest.raises(DomainError) as exc:
        rules.transition(current, target)
    assert exc.value.code == "INVALID_TRANSITION"


def test_m1_23_unknown_status() -> None:
    with pytest.raises(DomainError) as exc:
        rules.transition("pending_review", "teleported")
    assert exc.value.code == "UNKNOWN_STATUS"


def test_every_status_has_label() -> None:
    assert set(rules.STATUS_LABELS) == set(rules.TRANSITIONS)


# ---------- 審核 ----------
def test_f_rec_3_reject_requires_reason() -> None:
    with pytest.raises(DomainError) as exc:
        rules.review_target("rejected", None)
    assert exc.value.code == "REJECT_REASON_REQUIRED"
    assert rules.review_target("rejected", "competitor") == "rejected"


def test_f_rec_3_unknown_reason_and_decision() -> None:
    with pytest.raises(DomainError):
        rules.review_target("rejected", "because")
    with pytest.raises(DomainError):
        rules.review_target("maybe", None)
    with pytest.raises(DomainError):
        rules.review_target("approved", "competitor")


# ---------- 認領與鎖定 ----------
def test_m1_26_claim_free_company() -> None:
    got = rules.claim(Ownership(None, None), user_id=1, now=NOW, lock_days=30)
    assert got.owner_id == 1
    assert got.locked_until == NOW + timedelta(days=30)


def test_m1_26_cannot_claim_company_locked_by_other() -> None:
    locked = Ownership(owner_id=2, locked_until=NOW + timedelta(days=1))
    with pytest.raises(DomainError) as exc:
        rules.claim(locked, user_id=1, now=NOW, lock_days=30)
    assert exc.value.code == "COMPANY_LOCKED"


def test_m1_26_can_claim_after_lock_expires() -> None:
    expired = Ownership(owner_id=2, locked_until=NOW - timedelta(seconds=1))
    assert rules.claim(expired, user_id=1, now=NOW, lock_days=30).owner_id == 1


def test_m1_26_reclaim_extends_own_lock() -> None:
    mine = Ownership(owner_id=1, locked_until=NOW + timedelta(days=1))
    assert rules.claim(mine, user_id=1, now=NOW, lock_days=30).locked_until == NOW + timedelta(days=30)


def test_m1_26_release_only_by_owner_or_manager() -> None:
    owned = Ownership(owner_id=2, locked_until=NOW + timedelta(days=5))
    with pytest.raises(DomainError):
        rules.release(owned, user_id=1, is_manager=False)
    assert rules.release(owned, user_id=2, is_manager=False).owner_id is None
    assert rules.release(owned, user_id=1, is_manager=True).owner_id is None


def test_m1_26_assign_only_by_manager() -> None:
    with pytest.raises(DomainError):
        rules.assign(3, NOW, 30, is_manager=False)
    assert rules.assign(3, NOW, 30, is_manager=True).owner_id == 3


def test_m1_26_locked_company_can_only_be_changed_by_owner_or_manager() -> None:
    owned = Ownership(owner_id=2, locked_until=NOW + timedelta(days=5))
    with pytest.raises(DomainError):
        rules.ensure_can_act(owned, user_id=1, now=NOW, is_manager=False)
    rules.ensure_can_act(owned, user_id=2, now=NOW, is_manager=False)
    rules.ensure_can_act(owned, user_id=1, now=NOW, is_manager=True)
