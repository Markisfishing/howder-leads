"""migration 0007：待辦提醒 view（M3-10a、F-CASE-3）。條件只在 view，這裡直接用資料驗證。"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppUser, CaseUpdate, Company, SalesCase, v_case_reminder


def _case(db: Session, status: str, sent_days_ago: int, follow_up: date | None = None, tax: str = "1") -> SalesCase:
    user = db.scalar(select(AppUser)) or AppUser(email="sales1@example.com", display_name="s", role="sales")
    db.add(user)
    company = Company(tax_id=tax.zfill(8), name=f"公司{tax}", status="sent")
    db.add(company)
    db.flush()
    when = datetime.now(UTC) - timedelta(days=sent_days_ago)
    case = SalesCase(
        company_id=company.company_id,
        owner_id=user.user_id,
        origin="email",
        status=status,
        opened_at=when,
        next_follow_up=follow_up,
    )
    db.add(case)
    db.flush()
    db.add(CaseUpdate(case_id=case.case_id, channel="system", result="sent", created_at=when))
    db.flush()
    return case


def _kinds(db: Session, case: SalesCase) -> set[str]:
    return set(db.scalars(select(v_case_reminder.c.kind).where(v_case_reminder.c.case_id == case.case_id)))


def test_f_case_3_overdue_report_after_7_days(db: Session) -> None:
    assert _kinds(db, _case(db, "sent", 8, tax="1")) == {"overdue_report"}
    assert _kinds(db, _case(db, "sent", 6, tax="2")) == set()
    assert _kinds(db, _case(db, "replied", 8, tax="3")) == set()  # 有回填就不算


def test_f_case_3_follow_up_due(db: Session) -> None:
    past = date.today() - timedelta(days=2)
    future = date.today() + timedelta(days=5)
    assert _kinds(db, _case(db, "replied", 1, past, tax="4")) == {"follow_up_due"}
    assert _kinds(db, _case(db, "replied", 1, future, tax="5")) == set()


def test_f_case_3_no_response_suggests_visit(db: Session) -> None:
    assert _kinds(db, _case(db, "no_response", 15, tax="6")) == {"no_response"}


def test_f_case_3_closed_case_has_no_reminder(db: Session) -> None:
    case = _case(db, "sent", 30, date.today() - timedelta(days=3), tax="7")
    case.status, case.closed_at = "lost", datetime.now(UTC)
    db.flush()
    assert _kinds(db, case) == set()
