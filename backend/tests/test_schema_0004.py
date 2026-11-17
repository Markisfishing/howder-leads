"""M2-01a migration 0004：聯絡人來源 CHECK。"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _company(db: Session) -> int:
    return int(
        db.execute(
            text(
                "INSERT INTO company (tax_id, name, status) "
                "VALUES ('90000001', '測試公司', 'approved') RETURNING company_id"
            )
        ).scalar_one()
    )


def test_m2_01a_contact_source_accepts_known_values(db: Session) -> None:
    cid = _company(db)
    for i, source in enumerate(["website", "business_card", "referral", "exhibition", "manual"]):
        db.execute(
            text("INSERT INTO contact (company_id, email, source) VALUES (:c, :e, :s)"),
            {"c": cid, "e": f"c{i}@example.com", "s": source},
        )
    assert db.execute(text("SELECT count(*) FROM contact")).scalar_one() == 5


def test_m2_01a_contact_source_rejects_unknown_value(db: Session) -> None:
    cid = _company(db)
    with pytest.raises(IntegrityError):
        db.execute(
            text("INSERT INTO contact (company_id, email, source) VALUES (:c, 'x@example.com', 'scraped')"),
            {"c": cid},
        )
    db.rollback()
