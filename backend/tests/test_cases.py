"""案件追蹤整合測試：寄出開案、加入追蹤、回填帶動公司狀態、權限、催辦（M3-09、M3-10b）。

全部用假的寄信實作與 @example.com 假資料。
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select, update

from app.models import ActivityLog, CaseUpdate, Company, Job, SalesCase
from app.services import reminder_service
from tests.test_campaigns import World


def _send(world: World, n: int = 1) -> list[int]:
    """寄出 n 封（公司 10000001…），回傳公司 id。"""
    targets = [world.ids["10000001"], world.ids["10000002"], world.ids["10000003"]][:n]
    cid = world.create(targets)["campaign"]["campaign_id"]
    world.worker()
    world.client.post(f"/api/v1/campaigns/{cid}/approve-all", json={"confirm": True}, headers=world.sales1)
    world.client.post(f"/api/v1/campaigns/{cid}/send", json={}, headers=world.sales1)
    world.worker()
    return targets


def _cases(world: World, headers: dict[str, str] | None = None, **params: object) -> dict:  # type: ignore[type-arg]
    res = world.client.get("/api/v1/cases", params=params, headers=headers or world.sales1)
    assert res.status_code == 200, res.text
    return dict(res.json())


def _update(world: World, case_id: int, headers: dict[str, str] | None = None, **body: object):  # type: ignore[no-untyped-def]
    payload = {"channel": "phone", "result": "replied", **body}
    return world.client.post(f"/api/v1/cases/{case_id}/updates", json=payload, headers=headers or world.sales1)


# ---------- 開案（F-CASE-1）----------
def test_f_case_1_send_opens_case(world: World) -> None:
    [company] = _send(world)
    out = _cases(world)
    assert out["counts"]["sent"] == 1
    case = out["items"][0]
    assert case["case_no"].startswith("C-") and case["status"] == "sent" and case["origin"] == "email"
    assert case["company_id"] == company and case["contact_email"] == "buyer0@example.com"
    detail = world.client.get(f"/api/v1/cases/{case['case_id']}", headers=world.sales1).json()
    assert [u["result"] for u in detail["timeline"]] == ["sent"]
    assert detail["timeline"][0]["channel"] == "system"


def test_f_rec_9_add_tracking_and_later_email_joins_same_case(world: World) -> None:
    a = world.ids["10000001"]
    res = world.client.post("/api/v1/cases", json={"company_ids": [a]}, headers=world.sales1)
    assert res.status_code == 201, res.text
    assert res.json()[0]["status"] == "tracking"
    world.db.expire_all()
    assert world.db.get(Company, a).owner_id is not None  # type: ignore[union-attr]  # 加入追蹤時認領

    again = world.client.post("/api/v1/cases", json={"company_ids": [a]}, headers=world.sales1)
    assert again.json()["error"]["code"] == "TRACK_REJECTED"  # 已有進行中的案件

    _send(world)  # 之後再寄信 → 同一件案件
    out = _cases(world)
    assert len(out["items"]) == 1 and out["items"][0]["status"] == "sent"


def test_f_rec_9_tracking_rejects_whole_batch(world: World) -> None:
    pending = world.ids["10000004"]  # 待審，不能追蹤
    res = world.client.post(
        "/api/v1/cases", json={"company_ids": [world.ids["10000001"], pending]}, headers=world.sales1
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "TRACK_REJECTED"
    assert world.db.scalar(select(func.count()).select_from(SalesCase)) == 0


# ---------- 回填（F-CASE-2）----------
def test_f_case_2_update_moves_company_through_states(world: World) -> None:
    [company] = _send(world)
    case_id = _cases(world)["items"][0]["case_id"]
    follow = (date.today() + timedelta(days=3)).isoformat()
    res = _update(world, case_id, result="negotiating", note="客戶要報價", next_follow_up=follow)
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "negotiating" and res.json()["next_follow_up"] == follow
    assert world.status(company) == "meeting"  # sent → replied → meeting

    res = _update(world, case_id, channel="visit", result="won", amount_twd=120000)
    body = res.json()
    assert body["status"] == "won" and body["closed_at"] and body["amount_twd"] == "120000"
    assert world.status(company) == "won"
    changes = world.db.scalars(
        select(ActivityLog.to_value)
        .where(ActivityLog.company_id == company, ActivityLog.action == "status_change")
        .order_by(ActivityLog.log_id)  # 沒有排序時順序不保證，偶爾會讓這個測試不穩
    ).all()
    assert changes[-3:] == ["replied", "meeting", "won"]  # 每一步都留紀錄
    assert _update(world, case_id).json()["error"]["code"] == "CASE_CLOSED"


def test_f_case_2_invalid_update_rejected(world: World) -> None:
    _send(world)
    case_id = _cases(world)["items"][0]["case_id"]
    assert _update(world, case_id, result="lost", amount_twd=5).json()["error"]["code"] == "AMOUNT_ONLY_WHEN_WON"
    assert _update(world, case_id, channel="system").status_code == 422  # 系統管道不能手動選


def test_f_case_2_tracking_case_company_from_approved(world: World) -> None:
    a = world.ids["10000002"]
    case_id = world.client.post("/api/v1/cases", json={"company_ids": [a]}, headers=world.sales1).json()[0]["case_id"]
    assert _update(world, case_id, result="replied").status_code == 201
    assert world.status(a) == "replied"


# ---------- 權限（F-CASE-4）----------
def test_f_case_4_sales_sees_only_own_cases(world: World) -> None:
    _send(world)
    case_id = _cases(world)["items"][0]["case_id"]
    assert _cases(world, world.sales2)["items"] == []
    assert world.client.get(f"/api/v1/cases/{case_id}", headers=world.sales2).status_code == 404
    assert _update(world, case_id, headers=world.sales2).status_code == 404
    assert len(_cases(world, world.manager)["items"]) == 1  # 主管看全部


def test_f_case_4_filter_and_export(world: World) -> None:
    _send(world, 2)
    case_id = _cases(world)["items"][0]["case_id"]
    _update(world, case_id)
    out = _cases(world, status="replied")
    assert [c["case_id"] for c in out["items"]] == [case_id]
    assert out["counts"] == {**out["counts"], "sent": 1, "replied": 1}
    csv = world.client.get("/api/v1/cases/export", headers=world.sales1)
    assert csv.headers["content-type"].startswith("text/csv")
    text = csv.content.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("案件編號,公司,狀態")
    assert "@example.com" not in text  # 匯出不含 email


# ---------- 催辦（F-CASE-3）----------
def _age(world: World, days: int) -> None:
    """把所有案件的寄出時間往前推（view 用資料庫的 now()）。"""
    when = datetime.now(UTC) - timedelta(days=days)
    world.db.execute(update(SalesCase).values(opened_at=when))
    world.db.execute(update(CaseUpdate).where(CaseUpdate.result == "sent").values(created_at=when))
    world.db.commit()


def test_f_case_3_overdue_filter_and_reminders(world: World) -> None:
    _send(world, 2)
    _age(world, 8)
    rem = {r["kind"]: r["count"] for r in world.client.get("/api/v1/reminders", headers=world.sales1).json()}
    assert rem["overdue_report"] == 2 and rem["no_response"] == 0
    assert "pending_review" in rem
    first = _cases(world)["items"][0]
    assert first["reminders"] == ["overdue_report"]
    _update(world, first["case_id"])  # 回填後就不算逾期
    assert len(_cases(world, overdue=True)["items"]) == 1
    assert world.client.get("/api/v1/reminders", headers=world.sales2).json()[0]["count"] == 0


def test_f_case_3_daily_job_marks_no_response_and_reschedules(world: World) -> None:
    _send(world, 2)
    _age(world, 15)
    case_id = _cases(world)["items"][0]["case_id"]
    _update(world, case_id)  # 這件已回覆，不會被標成無回應
    reminder_service.ensure_daily_job(world.db, world.clock[0])
    reminder_service.ensure_daily_job(world.db, world.clock[0])  # 重複呼叫不會排兩筆
    world.worker()
    out = _cases(world)
    assert out["counts"]["no_response"] == 1 and out["counts"]["replied"] == 1
    no_resp = next(c for c in out["items"] if c["status"] == "no_response")
    assert no_resp["reminders"] == ["no_response"]
    detail = world.client.get(f"/api/v1/cases/{no_resp['case_id']}", headers=world.sales1).json()
    assert detail["timeline"][-1]["channel"] == "system" and detail["timeline"][-1]["result"] == "no_response"
    queued = world.db.scalars(select(Job).where(Job.kind == "case_daily", Job.status == "queued")).all()
    assert len(queued) == 1 and queued[0].run_after > world.clock[0]  # 排好明天的


def test_f_case_3_next_daily_run_is_6am_taipei() -> None:
    now = datetime(2026, 11, 18, 0, 0, tzinfo=UTC)  # 台灣 08:00 → 明天 06:00
    assert reminder_service.next_daily_run(now) == datetime(2026, 11, 18, 22, 0, tzinfo=UTC)
    early = datetime(2026, 11, 17, 21, 0, tzinfo=UTC)  # 台灣 05:00 → 今天 06:00
    assert reminder_service.next_daily_run(early) == datetime(2026, 11, 17, 22, 0, tzinfo=UTC)


# ---------- 退訂（M3-04a、F-CASE-5）----------
def test_m3_04a_unsubscribe_from_case_closes_it(world: World) -> None:
    [company] = _send(world)
    case_id = _cases(world)["items"][0]["case_id"]
    res = world.client.post(f"/api/v1/cases/{case_id}/unsubscribe", json={}, headers=world.sales1)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "lost" and body["closed_at"]
    assert "客戶要求退訂，不再聯絡" in [u["note"] for u in body["timeline"]]
    assert body["contacts"][0]["unsubscribed"] is True
    assert world.status(company) == "do_not_contact"
    rem = {r["kind"]: r["count"] for r in world.client.get("/api/v1/reminders", headers=world.sales1).json()}
    assert rem["overdue_report"] == 0


def _second_contact(world: World, company: int) -> int:
    res = world.client.post(
        "/api/v1/contacts",
        json={"company_id": company, "email": "other@example.com", "source": "manual"},
        headers=world.sales1,
    )
    assert res.status_code == 201, res.text
    return int(res.json()["contact_id"])


def test_m3_17_case_unsubscribe_keeps_case_when_other_contact_left(world: World) -> None:
    [company] = _send(world)
    other = _second_contact(world, company)
    case_id = _cases(world)["items"][0]["case_id"]
    res = world.client.post(f"/api/v1/cases/{case_id}/unsubscribe", json={}, headers=world.sales1)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "sent" and body["closed_at"] is None  # 案件照常，可以改用其他聯絡人
    flags = {c["contact_id"]: c["unsubscribed"] for c in body["contacts"]}
    assert flags[other] is False and list(flags.values()).count(True) == 1
    assert world.status(company) != "do_not_contact"


def test_m3_17_case_unsubscribe_whole_company_closes_case(world: World) -> None:
    [company] = _send(world)
    other = _second_contact(world, company)
    case_id = _cases(world)["items"][0]["case_id"]
    res = world.client.post(f"/api/v1/cases/{case_id}/unsubscribe", json={"whole_company": True}, headers=world.sales1)
    body = res.json()
    assert body["status"] == "lost" and body["closed_at"]
    assert world.status(company) == "do_not_contact"
    # 其他聯絡人沒有被標成退訂（只是公司不再聯絡）
    assert {c["contact_id"]: c["unsubscribed"] for c in body["contacts"]}[other] is False


def test_m3_04a_unsubscribe_via_contact_api_also_closes_case(world: World) -> None:
    [company] = _send(world)
    case = _cases(world)["items"][0]
    world.client.post(f"/api/v1/contacts/{case['contact_id']}/unsubscribe", json={}, headers=world.sales2)
    assert _cases(world)["items"][0]["status"] == "lost"
    assert world.client.post(f"/api/v1/cases/{case['case_id']}/unsubscribe", headers=world.sales2).status_code == 404
