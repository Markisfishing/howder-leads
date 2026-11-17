"""migration 0010：v_case_fact、v_company_fact、v_kpi_summary 的回覆率改用案件（M3-12a、F-DASH-1～3）。"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppUser, CaseUpdate, Company, SalesCase, v_case_fact, v_company_fact, v_kpi_summary

NOW = datetime(2026, 11, 1, 2, 0, tzinfo=UTC)


def _user(db: Session) -> AppUser:
    u = AppUser(email="sales1@example.com", display_name="業務甲")
    db.add(u)
    db.flush()
    return u


def _case(db: Session, owner: AppUser, tax_id: str, results: list[str], status: str, **kw: object) -> SalesCase:
    """建一家公司與一件案件；results 依序寫進時間軸。"""
    company = Company(tax_id=tax_id, name=f"公司{tax_id}", status="sent", source=kw.pop("source", None))
    db.add(company)
    db.flush()
    closed = NOW if status in ("won", "lost") else None
    origin = "email" if "sent" in results else "tracking"
    case = SalesCase(
        company_id=company.company_id, owner_id=owner.user_id, origin=origin, status=status, closed_at=closed, **kw
    )
    db.add(case)
    db.flush()
    for r in results:
        db.add(CaseUpdate(case_id=case.case_id, channel="system", result=r, created_at=NOW))
    db.flush()
    return case


def test_m3_12a_case_fact_flags(db: Session) -> None:
    owner = _user(db)
    sent_only = _case(db, owner, "90000401", ["sent"], "sent", source="expo")
    replied = _case(db, owner, "90000402", ["sent", "replied"], "replied", source="expo")
    won = _case(db, owner, "90000403", ["sent", "replied", "won"], "won", amount_twd=Decimal("120000"))
    tracking_won = _case(db, owner, "90000404", ["won"], "won", amount_twd=Decimal("5000"))  # 沒寄信、加入追蹤
    lost_no_reply = _case(db, owner, "90000405", ["sent", "lost"], "lost", amount_twd=None)

    rows = {r.case_id: r for r in db.execute(select(v_case_fact))}
    flags = {cid: (rows[cid].is_sent, rows[cid].is_replied, rows[cid].is_won) for cid in rows}
    assert flags[sent_only.case_id] == (True, False, False)
    assert flags[replied.case_id] == (True, True, False)
    assert flags[won.case_id] == (True, True, True)
    assert flags[tracking_won.case_id] == (False, True, True)
    assert flags[lost_no_reply.case_id] == (True, False, False)
    assert rows[won.case_id].won_amount == Decimal("120000")
    assert rows[sent_only.case_id].source == "expo"
    assert rows[sent_only.case_id].sent_at == NOW


def test_m3_12a_kpi_reply_rate_from_cases(db: Session) -> None:
    """回覆率 = 已寄出且有回覆 ÷ 已寄出；寄出滿 10 件才算，不再讀 email_event。"""
    owner = _user(db)
    for i in range(10):
        results = ["sent", "replied"] if i < 3 else ["sent"]
        _case(db, owner, f"9000050{i}", results, "replied" if i < 3 else "sent")
    _case(db, owner, "90000510", ["won"], "won", amount_twd=Decimal("800"))  # 沒寄信，不進回覆率
    kpi = db.execute(select(v_kpi_summary)).mappings().one()
    assert (kpi["sent_total"], kpi["replied_total"], kpi["reply_rate"]) == (10, 3, Decimal("0.3000"))
    assert (kpi["won_total"], kpi["won_amount_twd"]) == (1, Decimal("800"))


def test_m3_12a_company_fact_funnel_flags(db: Session) -> None:
    owner = _user(db)
    case = _case(db, owner, "90000601", ["sent", "replied"], "replied")
    pending = Company(tax_id="90000602", name="待審", status="pending_review")
    db.add(pending)
    db.flush()
    rows = {r.company_id: r for r in db.execute(select(v_company_fact))}
    a, p = rows[case.company_id], rows[pending.company_id]
    assert (a.is_approved, a.is_sent, a.is_replied, a.is_won, a.first_sent_at) == (True, True, True, False, NOW)
    assert (p.is_approved, p.is_sent, p.is_replied) == (False, False, False)
