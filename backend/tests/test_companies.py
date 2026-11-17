"""推薦清單、審核、認領、修正、手動加入、KPI（M1-24 ~ M1-30、F-REC-1 ~ F-REC-6）。"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActivityLog, Review
from tests.factories import csv_bytes

Headers = Callable[[str], dict[str, str]]


@pytest.fixture
def ids(client: TestClient, as_user: Headers) -> dict[str, int]:
    """匯入 4 家假公司，回傳 統編 → company_id。"""
    admin = as_user("admin@example.com")
    batch = client.post("/api/v1/imports", files={"file": ("a.csv", csv_bytes(), "text/csv")}, headers=admin).json()
    client.post(f"/api/v1/imports/{batch['batch_id']}/commit", headers=admin)
    items = client.get("/api/v1/companies", headers=admin).json()["items"]
    return {c["tax_id"]: c["company_id"] for c in items}


@pytest.fixture
def sales1(as_user: Headers) -> dict[str, str]:
    return as_user("sales1@example.com")


@pytest.fixture
def sales2(as_user: Headers) -> dict[str, str]:
    return as_user("sales2@example.com")


# ---------- 清單（F-REC-1、F-REC-2）----------
def test_f_rec_1_sorted_by_stars(client: TestClient, ids: dict[str, int], sales1: dict[str, str]) -> None:
    body = client.get("/api/v1/companies", headers=sales1).json()
    assert body["total"] == 4
    assert [c["stars"] for c in body["items"]] == [5, 4, 2, 1]
    first = body["items"][0]
    assert first["industry"] == "工業自動化與機械設備"
    assert first["reason"] and first["status"] == "pending_review"


def test_f_rec_2_filters(client: TestClient, ids: dict[str, int], sales1: dict[str, str]) -> None:
    def tax_ids(params: str) -> set[str]:
        return {c["tax_id"] for c in client.get(f"/api/v1/companies?{params}", headers=sales1).json()["items"]}

    assert tax_ids("stars=5&stars=4") == {"10000001", "10000002"}
    assert tax_ids("has_website=false") == {"10000002", "10000004"}
    assert tax_ids("competitor=true") == {"10000003"}
    assert tax_ids("q=電機") == {"10000002"}
    assert tax_ids("q=1000000") == set(ids)
    assert tax_ids("owner=none") == set(ids)
    assert tax_ids("owner=me") == set()


def test_f_rec_1_pagination(client: TestClient, ids: dict[str, int], sales1: dict[str, str]) -> None:
    body = client.get("/api/v1/companies?page=2&page_size=3", headers=sales1).json()
    assert body["total"] == 4 and len(body["items"]) == 1


# ---------- 審核（F-REC-3、M1-24、M1-25）----------
def test_f_rec_3_batch_approve(client: TestClient, ids: dict[str, int], sales1: dict[str, str], db: Session) -> None:
    targets = [ids["10000001"], ids["10000002"]]
    res = client.post("/api/v1/reviews", json={"company_ids": targets, "decision": "approved"}, headers=sales1)
    assert res.status_code == 200 and res.json()["updated"] == 2
    statuses = {c["company_id"]: c["status"] for c in client.get("/api/v1/companies", headers=sales1).json()["items"]}
    assert statuses[targets[0]] == statuses[targets[1]] == "approved"
    logs = list(db.scalars(select(ActivityLog).where(ActivityLog.action == "status_change")))
    assert {(log.from_value, log.to_value) for log in logs} == {("pending_review", "approved")}
    assert len(logs) == 2


def test_f_rec_3_reject_requires_reason(client: TestClient, ids: dict[str, int], sales1: dict[str, str]) -> None:
    body = {"company_ids": [ids["10000004"]], "decision": "rejected"}
    res = client.post("/api/v1/reviews", json=body, headers=sales1)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "REJECT_REASON_REQUIRED"


def test_f_rec_3_reject_with_reason_and_industry_correction(
    client: TestClient, ids: dict[str, int], sales1: dict[str, str], db: Session
) -> None:
    body = {
        "company_ids": [ids["10000003"]],
        "decision": "rejected",
        "reject_reason": "wrong_industry",
        "corrected_industry_id": 3,
        "note": "其實是配電盤廠",
    }
    assert client.post("/api/v1/reviews", json=body, headers=sales1).status_code == 200
    detail = client.get(f"/api/v1/companies/{ids['10000003']}", headers=sales1).json()
    assert detail["status"] == "rejected"
    assert detail["industry_id"] == 3 and detail["model_industry_id"] != 3
    review = db.scalar(select(Review))
    assert review is not None and review.reject_reason == "wrong_industry"


def test_f_rec_3_batch_is_all_or_nothing(client: TestClient, ids: dict[str, int], sales1: dict[str, str]) -> None:
    client.post("/api/v1/reviews", json={"company_ids": [ids["10000001"]], "decision": "approved"}, headers=sales1)
    body = {"company_ids": [ids["10000001"], ids["10000002"]], "decision": "approved"}
    res = client.post("/api/v1/reviews", json=body, headers=sales1)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "REVIEW_REJECTED"
    detail = client.get(f"/api/v1/companies/{ids['10000002']}", headers=sales1).json()
    assert detail["status"] == "pending_review"  # 沒有被部分寫入


def test_f_rec_3_re_review_rejected_company(client: TestClient, ids: dict[str, int], sales1: dict[str, str]) -> None:
    cid = ids["10000004"]
    reject = {"company_ids": [cid], "decision": "rejected", "reject_reason": "no_demand"}
    client.post("/api/v1/reviews", json=reject, headers=sales1)
    res = client.post("/api/v1/reviews", json={"company_ids": [cid], "decision": "approved"}, headers=sales1)
    assert res.status_code == 200


# ---------- 認領與鎖定（M1-26）----------
def test_m1_26_claim_locks_company_for_others(
    client: TestClient, ids: dict[str, int], sales1: dict[str, str], sales2: dict[str, str]
) -> None:
    cid = ids["10000001"]
    res = client.post(f"/api/v1/companies/{cid}/claim", headers=sales1)
    assert res.status_code == 200
    assert res.json()["owner_name"] == "sales1"
    assert res.json()["owner_locked_until"] is not None

    other = client.post(f"/api/v1/companies/{cid}/claim", headers=sales2)
    assert other.json()["error"]["code"] == "COMPANY_LOCKED"
    review = client.post("/api/v1/reviews", json={"company_ids": [cid], "decision": "approved"}, headers=sales2)
    assert review.status_code == 409
    patch = client.patch(f"/api/v1/companies/{cid}", json={"website_url": "https://x.example.com"}, headers=sales2)
    assert patch.json()["error"]["code"] == "COMPANY_LOCKED"
    assert client.get("/api/v1/companies?owner=me", headers=sales1).json()["total"] == 1


def test_m1_26_release_and_manager_assign(
    client: TestClient, ids: dict[str, int], sales1: dict[str, str], sales2: dict[str, str], as_user: Headers
) -> None:
    cid = ids["10000001"]
    client.post(f"/api/v1/companies/{cid}/claim", headers=sales1)
    assert client.post(f"/api/v1/companies/{cid}/release", headers=sales2).json()["error"]["code"] == "NOT_OWNER"

    manager = as_user("manager@example.com")
    sales2_id = client.get("/api/v1/me", headers=sales2).json()["user_id"]
    assert (
        client.post(f"/api/v1/companies/{cid}/assign", json={"user_id": sales2_id}, headers=sales1).status_code == 403
    )
    res = client.post(f"/api/v1/companies/{cid}/assign", json={"user_id": sales2_id}, headers=manager)
    assert res.json()["owner_id"] == sales2_id

    assert client.post(f"/api/v1/companies/{cid}/release", headers=sales2).json()["owner_id"] is None


# ---------- 詳情與修正（F-REC-4）----------
def test_f_rec_4_detail_and_corrections(client: TestClient, ids: dict[str, int], sales1: dict[str, str]) -> None:
    cid = ids["10000002"]
    detail = client.get(f"/api/v1/companies/{cid}", headers=sales1).json()
    assert detail["registered_products"] == "281發電輸電配電機械"
    assert detail["priority_label"] == "可開發"
    assert detail["website_url"] is None

    patched = client.patch(
        f"/api/v1/companies/{cid}",
        json={"website_url": "https://motor.example.com", "industry_id": 3, "note": "電話確認過"},
        headers=sales1,
    ).json()
    assert patched["website_url"] == "https://motor.example.com"
    assert patched["website_verified"] is True
    assert patched["industry_id"] == 3
    assert {a["action"] for a in patched["activities"]} >= {"update_website", "update_industry", "note"}


def test_f_rec_4_verified_website_not_overwritten_by_import(
    client: TestClient, ids: dict[str, int], sales1: dict[str, str], as_user: Headers
) -> None:
    cid = ids["10000001"]
    client.patch(f"/api/v1/companies/{cid}", json={"website_url": "https://right.example.com"}, headers=sales1)
    admin = as_user("admin@example.com")
    batch = client.post("/api/v1/imports", files={"file": ("a.csv", csv_bytes(), "text/csv")}, headers=admin).json()
    client.post(f"/api/v1/imports/{batch['batch_id']}/commit", headers=admin)
    assert client.get(f"/api/v1/companies/{cid}", headers=sales1).json()["website_url"] == "https://right.example.com"


def test_unknown_company_404(client: TestClient, sales1: dict[str, str]) -> None:
    res = client.get("/api/v1/companies/999999", headers=sales1)
    assert res.status_code == 404 and res.json()["error"]["code"] == "COMPANY_NOT_FOUND"


# ---------- 手動加入（F-REC-6）----------
def test_f_rec_6_manual_add(client: TestClient, ids: dict[str, int], sales1: dict[str, str]) -> None:
    body = {"tax_id": "20000001", "name": "業務自己找到的公司", "industry_id": 1}
    res = client.post("/api/v1/companies", json=body, headers=sales1)
    assert res.status_code == 201
    created = res.json()
    assert created["added_manually"] is True
    assert created["status"] == "pending_review"
    assert created["stars"] == 0  # 模型沒評分

    dup = client.post("/api/v1/companies", json={"tax_id": "10000001", "name": "重複"}, headers=sales1)
    assert dup.json()["error"]["code"] == "COMPANY_EXISTS"
    bad = client.post("/api/v1/companies", json={"tax_id": "abcdefgh", "name": "壞統編"}, headers=sales1)
    assert bad.json()["error"]["code"] == "INVALID_TAX_ID"


# ---------- KPI 與維度（F-REC-5）----------
def test_f_rec_5_kpis(client: TestClient, ids: dict[str, int], sales1: dict[str, str]) -> None:
    client.post("/api/v1/reviews", json={"company_ids": [ids["10000001"]], "decision": "approved"}, headers=sales1)
    kpi = client.get("/api/v1/metrics/kpis", headers=sales1).json()
    assert kpi["pending_review"] == 3
    assert kpi["total_companies"] == 4
    assert kpi["five_star"] == 1
    assert kpi["sent_7d"] == 0
    assert kpi["reply_rate"] is None  # 寄出未滿 10 封


def test_dimensions(client: TestClient, sales1: dict[str, str]) -> None:
    body = client.get("/api/v1/dimensions", headers=sales1).json()
    assert len(body["industries"]) == 19
    assert [p["stars"] for p in body["priorities"]] == [5, 4, 2, 1]
    assert "wrong_industry" in body["reject_reasons"]


def test_m1_38_export_reviews_csv(
    client: TestClient, ids: dict[str, int], sales1: dict[str, str], as_user: Headers
) -> None:
    reject = {"company_ids": [ids["10000004"]], "decision": "rejected", "reject_reason": "no_demand"}
    client.post("/api/v1/reviews", json=reject, headers=sales1)
    assert client.get("/api/v1/admin/reviews/export", headers=sales1).status_code == 403
    res = client.get("/api/v1/admin/reviews/export", headers=as_user("admin@example.com"))
    assert res.status_code == 200
    text = res.content.decode("utf-8-sig")
    assert "排除原因" in text.splitlines()[0]
    assert "no_demand" in text and "10000004" in text
