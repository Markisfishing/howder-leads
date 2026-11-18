"""總覽 API（M3-12b、F-DASH-1～4）。"""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppUser, CaseUpdate, Company, ImportBatch, SalesCase
from app.services.metrics_service import rate

Headers = Callable[[str], dict[str, str]]
NOV1 = datetime(2026, 11, 1, 2, 0, tzinfo=UTC)  # 台灣 11/1 10:00
NOV10 = datetime(2026, 11, 10, 2, 0, tzinfo=UTC)


class Data:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.n = 0

    def user(self, email: str) -> AppUser:
        return db_user(self.db, email)

    def case(
        self,
        owner: AppUser,
        results: list[str],
        status: str,
        *,
        source: str | None = None,
        at: datetime = NOV1,
        amount: int | None = None,
    ) -> SalesCase:
        self.n += 1
        # 寄信不會自動認領公司（owner_id 留空），漏斗要依「案件」的負責業務算
        company = Company(tax_id=f"9100{self.n:04d}", name=f"公司{self.n}", status="sent", source=source)
        self.db.add(company)
        self.db.flush()
        case = SalesCase(
            company_id=company.company_id,
            owner_id=owner.user_id,
            origin="email" if "sent" in results else "tracking",
            status=status,
            amount_twd=amount,
            closed_at=at if status in ("won", "lost") else None,
        )
        self.db.add(case)
        self.db.flush()
        for r in results:
            self.db.add(CaseUpdate(case_id=case.case_id, channel="system", result=r, created_at=at))
        self.db.flush()
        return case


def db_user(db: Session, email: str) -> AppUser:
    return db.scalars(select(AppUser).where(AppUser.email == email)).one()


@pytest.fixture
def seeded(db: Session, client: TestClient, as_user: Headers) -> dict[str, dict[str, str]]:
    """業務甲：expo 來源寄 12 件、回覆 4 件、其中成交 1 件（11/1）；b2b 寄 3 件（11/10）。業務乙：寄 1 件。"""
    heads = {
        "s1": as_user("sales1@example.com"),
        "s2": as_user("sales2@example.com"),
        "mgr": as_user("manager@example.com"),
    }
    for h in heads.values():
        client.get("/api/v1/me", headers=h)
    d = Data(db)
    s1, s2 = db_user(db, "sales1@example.com"), db_user(db, "sales2@example.com")
    for i in range(12):
        if i == 0:
            d.case(s1, ["sent", "replied", "won"], "won", source="expo", amount=50000)
        elif i < 4:
            d.case(s1, ["sent", "replied"], "replied", source="expo")
        else:
            d.case(s1, ["sent"], "sent", source="expo")
    for _ in range(3):
        d.case(s1, ["sent"], "sent", source="b2b", at=NOV10)
    d.case(s2, ["sent"], "sent")
    db.add(Company(tax_id="91009999", name="待審公司", status="pending_review"))
    db.add(ImportBatch(status="committed", funnel={"資料庫總數": 39000, "產品命中": 900}))
    db.commit()
    return heads


def _get(client: TestClient, headers: dict[str, str], query: str = "") -> dict:
    res = client.get(f"/api/v1/metrics/overview?{query}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_f_dash_1_kpis_for_sales_are_own_cases(client: TestClient, seeded: dict[str, dict[str, str]]) -> None:
    body = _get(client, seeded["s1"])
    k = body["kpis"]
    assert (k["sent"], k["replied"], k["won"], k["won_amount_twd"]) == (15, 4, 1, "50000")
    assert k["reply_rate"] == "0.2667"
    assert k["companies"] == 17  # 名單池是共用的
    assert body["scope_owner_id"] is not None


def test_f_dash_1_manager_sees_team_and_can_filter_owner(
    client: TestClient, seeded: dict[str, dict[str, str]], db: Session
) -> None:
    assert _get(client, seeded["mgr"])["kpis"]["sent"] == 16
    s2 = db_user(db, "sales2@example.com").user_id
    assert _get(client, seeded["mgr"], f"owner={s2}")["kpis"]["sent"] == 1
    # 業務指定別人也只會看到自己的
    assert _get(client, seeded["s1"], f"owner={s2}")["kpis"]["sent"] == 15


def test_f_dash_1_date_range_uses_taiwan_sent_date(client: TestClient, seeded: dict[str, dict[str, str]]) -> None:
    k = _get(client, seeded["s1"], "from=2026-11-05&to=2026-11-10")["kpis"]
    assert (k["sent"], k["reply_rate"]) == (3, None)  # 少於 10 件不算比例
    res = client.get("/api/v1/metrics/overview?from=2026-11-10&to=2026-11-01", headers=seeded["s1"])
    assert res.json()["error"]["code"] == "INVALID_DATE_RANGE"


def test_f_dash_2_funnel_with_retention(client: TestClient, seeded: dict[str, dict[str, str]]) -> None:
    body = _get(client, seeded["mgr"])
    stages = {s["key"]: (s["count"], s["rate"]) for s in body["funnel"]}
    assert stages["list"] == (17, None)
    assert stages["approved"] == (16, "0.9412")
    assert stages["sent"] == (16, "1.0000")
    assert stages["replied"] == (4, "0.2500")
    assert stages["won"] == (1, "0.2500")
    assert body["mle_funnel"] == {"資料庫總數": 39000, "產品命中": 900}


def test_f_dash_2_ignores_json_null_mle_funnel(
    client: TestClient, seeded: dict[str, dict[str, str]], db: Session
) -> None:
    db.add(ImportBatch(status="committed", funnel=None))
    db.commit()

    assert _get(client, seeded["mgr"])["mle_funnel"] == {"資料庫總數": 39000, "產品命中": 900}


def test_f_dash_2_sales_funnel_counts_own_cases(client: TestClient, seeded: dict[str, dict[str, str]]) -> None:
    """M3-14 發現的 bug：寄信沒認領公司時，業務的漏斗「已寄信」變成 0。"""
    stages = {s["key"]: s["count"] for s in _get(client, seeded["s1"])["funnel"]}
    assert (stages["sent"], stages["replied"], stages["won"]) == (15, 4, 1)
    dated = {s["key"]: s["count"] for s in _get(client, seeded["s1"], "from=2026-11-05")["funnel"]}
    assert dated["sent"] == 3


def test_f_dash_3_source_rates_flag_small_samples(client: TestClient, seeded: dict[str, dict[str, str]]) -> None:
    rows = _get(client, seeded["mgr"])["by_source"]
    assert [(r["source"], r["sent"], r["replied"], r["insufficient"]) for r in rows] == [
        ("expo", 12, 4, False),
        ("b2b", 3, 0, True),
        ("未標示", 1, 0, True),
    ]
    assert rows[0]["reply_rate"] == "0.3333" and rows[1]["reply_rate"] is None


def test_f_dash_4_reminder_counts(client: TestClient, seeded: dict[str, dict[str, str]]) -> None:
    reminders = {r["kind"]: r["count"] for r in _get(client, seeded["s1"])["reminders"]}
    assert reminders["pending_review"] == 1
    assert reminders["overdue_report"] >= 1  # 11/1 寄出、還沒回填
    assert set(reminders) == {"overdue_report", "follow_up_due", "no_response", "pending_review"}


def test_f_dash_rate_helper() -> None:
    assert rate(3, 9) is None
    assert rate(3, 10) == Decimal("0.3000")
    assert rate(0, 0, 1) is None
