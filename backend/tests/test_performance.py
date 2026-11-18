"""績效與名單品質 API（M4-01、M4-02；F-TRK-5、F-MLE-1）。資料沿用總覽測試的 seeded（全是假資料）。"""

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.factories import csv_bytes
from tests.test_overview import Data, db_user, seeded  # noqa: F401  （seeded 是 fixture）

Heads = dict[str, dict[str, str]]


def _get(client: TestClient, headers: dict[str, str], path: str) -> dict:  # type: ignore[type-arg]
    res = client.get(f"/api/v1/metrics/{path}", headers=headers)
    assert res.status_code == 200, res.text
    return dict(res.json())


def _rows(body: dict) -> dict[str, dict]:  # type: ignore[type-arg]
    return {r["key"]: r for r in body["items"]}


# ---------- 績效（M4-01）----------
def test_m4_01b_win_rate_by_source_matches_overview_definitions(client: TestClient, seeded: Heads) -> None:  # noqa: F811
    rows = _rows(_get(client, seeded["s1"], "win-rate?by=source"))
    expo, b2b = rows["expo"], rows["b2b"]
    assert (expo["sent"], expo["replied"], expo["won"], expo["won_amount_twd"]) == (12, 4, 1, "50000")
    assert (expo["reply_rate"], expo["win_rate"], expo["insufficient"]) == ("0.3333", "0.0833", False)
    # 寄出少於 10 件：不算比例，標樣本不足
    assert (b2b["sent"], b2b["reply_rate"], b2b["win_rate"], b2b["insufficient"]) == (3, None, None, True)


def test_m4_01b_insufficient_rows_sorted_last(client: TestClient, seeded: Heads) -> None:  # noqa: F811
    items = _get(client, seeded["s1"], "win-rate?by=source")["items"]
    assert [i["key"] for i in items] == ["expo", "b2b"]


def test_m4_01b_win_rate_by_stars_and_tag(client: TestClient, seeded: Heads) -> None:  # noqa: F811
    stars = _get(client, seeded["s1"], "win-rate?by=stars")["items"]
    assert sum(i["sent"] for i in stars) == 15  # 沒有分類的案件歸在「未評分」
    assert stars[0]["label"] == "未評分（手動加入）"
    tags = _get(client, seeded["s1"], "win-rate?by=tag")["items"]
    assert [(t["label"], t["sent"]) for t in tags] == [("（無標籤）", 15)]


def test_m4_01b_unknown_breakdown_rejected(client: TestClient, seeded: Heads) -> None:  # noqa: F811
    assert client.get("/api/v1/metrics/win-rate?by=nope", headers=seeded["s1"]).status_code == 422


def test_m4_01b_reps_sales_only_see_themselves_manager_sees_all(client: TestClient, seeded: Heads) -> None:  # noqa: F811
    mine = _get(client, seeded["s1"], "reps")
    assert len(mine["items"]) == 1 and mine["items"][0]["sent"] == 15 and mine["scope_owner_id"] is not None
    team = _get(client, seeded["mgr"], "reps")
    assert team["scope_owner_id"] is None
    assert [(r["sent"], r["won"]) for r in team["items"]] == [(15, 1), (1, 0)]  # 成交金額高的在前


def test_m4_01b_date_range_and_invalid_range(client: TestClient, seeded: Heads) -> None:  # noqa: F811
    rows = _rows(_get(client, seeded["s1"], "win-rate?by=source&from=2026-11-05&to=2026-11-10"))
    assert set(rows) == {"b2b"}
    res = client.get("/api/v1/metrics/reps?from=2026-11-10&to=2026-11-01", headers=seeded["s1"])
    assert res.json()["error"]["code"] == "INVALID_DATE_RANGE"


def test_m4_01a_case_perf_view_has_one_row_per_case(db: Session, seeded: Heads) -> None:  # noqa: F811
    cases = db.execute(text("SELECT count(*) FROM sales_case")).scalar_one()
    rows = db.execute(text("SELECT count(*), count(DISTINCT case_id) FROM v_case_perf")).one()
    assert rows[0] == rows[1] == cases  # 接模板、業務、標籤後不會讓一件案件變成多列


def test_m4_01b_templates_only_include_cases_with_template(client: TestClient, seeded: Heads) -> None:  # noqa: F811
    # seeded 的案件沒有經過邀請信批次（沒有模板）→ 不出現在模板表
    assert _get(client, seeded["mgr"], "templates")["items"] == []


# ---------- 名單品質（M4-02）----------
def _reject_some(client: TestClient, admin: dict[str, str], sales: dict[str, str]) -> None:
    batch = client.post("/api/v1/imports", files={"file": ("a.csv", csv_bytes(), "text/csv")}, headers=admin).json()
    client.post(f"/api/v1/imports/{batch['batch_id']}/commit", headers=admin)
    items = client.get("/api/v1/companies", headers=admin).json()["items"]
    ids = [c["company_id"] for c in items]
    for company_id, reason in zip(ids[:3], ["wrong_industry", "wrong_industry", "competitor"], strict=True):
        res = client.post(
            "/api/v1/reviews",
            json={"company_ids": [company_id], "decision": "rejected", "reject_reason": reason},
            headers=sales,
        )
        assert res.status_code == 200, res.text


def test_m4_02a_reject_reasons_report_for_manager(client: TestClient, as_user) -> None:  # type: ignore[no-untyped-def]
    admin, sales, manager = as_user("admin@example.com"), as_user("sales1@example.com"), as_user("manager@example.com")
    _reject_some(client, admin, sales)
    body = client.get("/api/v1/metrics/reject-reasons", headers=manager).json()
    assert body["total"] == 3
    assert [(i["reason"], i["count"], i["share"]) for i in body["items"]] == [
        ("wrong_industry", 2, "0.6667"),
        ("competitor", 1, "0.3333"),
    ]
    assert body["run_id"] == body["runs"][0]["run_id"]  # 預設最新一批
    same = client.get(f"/api/v1/metrics/reject-reasons?run_id={body['run_id']}", headers=manager).json()
    assert same["items"] == body["items"]
    other = client.get("/api/v1/metrics/reject-reasons?run_id=999999", headers=manager).json()
    assert (other["total"], other["items"]) == (0, [])


def test_m4_02a_reject_reasons_forbidden_for_sales(client: TestClient, as_user) -> None:  # type: ignore[no-untyped-def]
    res = client.get("/api/v1/metrics/reject-reasons", headers=as_user("sales1@example.com"))
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"


def test_m4_02a_reject_reasons_empty_without_any_run(client: TestClient, as_user) -> None:  # type: ignore[no-untyped-def]
    body = client.get("/api/v1/metrics/reject-reasons", headers=as_user("manager@example.com")).json()
    assert (body["run_id"], body["total"], body["items"]) == (None, 0, [])
