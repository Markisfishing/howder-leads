"""migration 0009：CSV 欄位規格 v1 的新欄位、CHECK 約束與 v_recommendation 新欄位（M3-06a、F-REC-7）。"""

from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Classification, Company, ModelRun, v_recommendation


def _company(db: Session, tax_id: str = "90000001", **kw: object) -> Company:
    c = Company(tax_id=tax_id, name="測試公司", **kw)
    db.add(c)
    db.flush()
    return c


def test_m3_06a_company_defaults(db: Session) -> None:
    c = _company(db)
    db.refresh(c)
    assert (c.country, c.url_status, c.source) == ("TW", "unchecked", None)


@pytest.mark.parametrize("field,value", [("country", "tw"), ("country", "T1"), ("url_status", "broken")])
def test_m3_06a_company_checks(db: Session, field: str, value: str) -> None:
    with pytest.raises(IntegrityError):
        _company(db, **{field: value})
    db.rollback()


def test_m3_06a_fit_stars_range(db: Session) -> None:
    c = _company(db)
    run = ModelRun(model_name="t")
    db.add(run)
    db.flush()
    db.add(Classification(company_id=c.company_id, run_id=run.run_id, fit_stars=Decimal("5.1")))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_m3_06a_view_fit_stars_falls_back_to_priority_stars(db: Session) -> None:
    """沒給 fit_stars 時用優先級對照的星等；有給就用小數星等。"""
    a = _company(db, "90000001", source="twincn", country="VN")
    b = _company(db, "90000002")
    run = ModelRun(model_name="t")
    db.add(run)
    db.flush()
    db.add(
        Classification(
            company_id=a.company_id,
            run_id=run.run_id,
            priority="A",
            fit_stars=Decimal("4.3"),
            product_type="端子台",
            tags=["PLC", "外銷"],
        )
    )
    db.add(Classification(company_id=b.company_id, run_id=run.run_id, priority="A"))
    db.flush()
    stars_a = db.execute(text("SELECT stars FROM dim_priority WHERE priority = 'A'")).scalar_one()
    rows = {r.company_id: r for r in db.execute(select(v_recommendation))}
    ra, rb = rows[a.company_id], rows[b.company_id]
    assert (ra.fit_stars, ra.country, ra.source, ra.product_type, ra.tags) == (
        Decimal("4.3"),
        "VN",
        "twincn",
        "端子台",
        ["PLC", "外銷"],
    )
    assert rb.fit_stars == Decimal(stars_a) and rb.tags == []
