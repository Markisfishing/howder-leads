"""migration 0006：案件與回填。"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AppUser, CaseUpdate, Company, SalesCase


def _setup(db: Session) -> tuple[Company, AppUser]:
    user = AppUser(email="sales1@example.com", display_name="sales1", role="sales")
    company = Company(tax_id="12345678", name="測試公司", status="sent")
    db.add_all([user, company])
    db.flush()
    return company, user


def test_m3_07a_case_no_generated(db: Session) -> None:
    company, user = _setup(db)
    case = SalesCase(company_id=company.company_id, owner_id=user.user_id, origin="email", status="sent")
    db.add(case)
    db.flush()
    db.refresh(case)
    assert case.case_no == f"C-{case.case_id:04d}"


def test_m3_07a_one_open_case_per_company(db: Session) -> None:
    company, user = _setup(db)
    db.add(SalesCase(company_id=company.company_id, owner_id=user.user_id, origin="email", status="sent"))
    db.flush()
    db.add(SalesCase(company_id=company.company_id, owner_id=user.user_id, origin="tracking", status="tracking"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_m3_07a_closed_status_requires_closed_at(db: Session) -> None:
    company, user = _setup(db)
    db.add(SalesCase(company_id=company.company_id, owner_id=user.user_id, origin="email", status="won"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


@pytest.mark.parametrize(("column", "value"), [("channel", "fax"), ("result", "maybe")])
def test_m3_07a_update_check_constraints(db: Session, column: str, value: str) -> None:
    company, user = _setup(db)
    case = SalesCase(company_id=company.company_id, owner_id=user.user_id, origin="email", status="sent")
    db.add(case)
    db.flush()
    fields = {"channel": "phone", "result": "replied", column: value}
    db.add(CaseUpdate(case_id=case.case_id, user_id=user.user_id, **fields))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_m3_07a_opportunity_removed(db: Session) -> None:
    assert db.execute(text("SELECT to_regclass('opportunity')")).scalar() is None
