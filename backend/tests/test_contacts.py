"""聯絡人 API（M2-01a、F-CASE-5、SPEC 9 個資）。所有 email 都是假的 @example.com。"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.domain import contact_rules
from app.domain.company_rules import DomainError
from app.models import ActivityLog, Company
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
def cid(ids: dict[str, int]) -> int:
    return ids["10000001"]


@pytest.fixture
def sales1(as_user: Headers) -> dict[str, str]:
    return as_user("sales1@example.com")


@pytest.fixture
def sales2(as_user: Headers) -> dict[str, str]:
    return as_user("sales2@example.com")


def _add(client: TestClient, headers: dict[str, str], company_id: int, **extra: object) -> dict[str, object]:
    body: dict[str, object] = {"company_id": company_id, "email": "buyer@example.com", "source": "website"}
    body.update(extra)
    res = client.post("/api/v1/contacts", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return dict(res.json())


def _logs(db: Session, action: str) -> list[ActivityLog]:
    db.expire_all()
    return list(db.scalars(select(ActivityLog).where(ActivityLog.action == action)))


# ---------- domain 規則 ----------
@pytest.mark.parametrize("raw", ["Buyer@Example.com", "  buyer@example.com  "])
def test_m2_01a_normalize_email_lowercases_and_strips(raw: str) -> None:
    assert contact_rules.normalize_email(raw) == "buyer@example.com"


@pytest.mark.parametrize(
    "raw", ["", "buyer", "buyer@", "@example.com", "buyer@example", "a b@example.com", "a@@b.com", "a..b@example.com"]
)
def test_m2_01a_normalize_email_rejects_bad_format(raw: str) -> None:
    with pytest.raises(DomainError) as e:
        contact_rules.normalize_email(raw)
    assert e.value.code == "INVALID_EMAIL"


def test_m2_01a_source_whitelist() -> None:
    assert contact_rules.check_source("business_card") == "business_card"
    with pytest.raises(DomainError) as e:
        contact_rules.check_source("scraped")
    assert e.value.code == "INVALID_SOURCE"


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_m2_01a_delete_reason_required(reason: str | None) -> None:
    with pytest.raises(DomainError) as e:
        contact_rules.check_delete_reason(reason)
    assert e.value.code == "DELETE_REASON_REQUIRED"


# ---------- 新增 ----------
def test_m2_01a_create_contact(client: TestClient, db: Session, cid: int, sales1: dict[str, str]) -> None:
    created = _add(client, sales1, cid, email=" Buyer@Example.COM ", name="王小明", title="採購", is_verified=True)
    assert created["email"] == "buyer@example.com"
    assert created["source"] == "website"
    assert created["unsubscribed"] is False

    detail = client.get(f"/api/v1/companies/{cid}", headers=sales1).json()
    assert [c["email"] for c in detail["contacts"]] == ["buyer@example.com"]
    assert detail["contacts"][0]["source"] == "website"
    assert detail["contacts"][0]["is_verified"] is True

    [log] = _logs(db, "contact_add")
    assert log.company_id == cid and log.to_value == str(created["contact_id"])
    assert "example.com" not in f"{log.from_value}{log.to_value}{log.note}"  # log 不記 email


def test_m2_01a_create_requires_source(client: TestClient, cid: int, sales1: dict[str, str]) -> None:
    res = client.post("/api/v1/contacts", json={"company_id": cid, "email": "buyer@example.com"}, headers=sales1)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"

    res = client.post(
        "/api/v1/contacts", json={"company_id": cid, "email": "buyer@example.com", "source": "scraped"}, headers=sales1
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_SOURCE"


def test_m2_01a_create_rejects_bad_email(client: TestClient, cid: int, sales1: dict[str, str]) -> None:
    res = client.post(
        "/api/v1/contacts", json={"company_id": cid, "email": "not-an-email", "source": "manual"}, headers=sales1
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_EMAIL"


def test_m2_01a_no_duplicate_email_in_same_company(
    client: TestClient, ids: dict[str, int], cid: int, sales1: dict[str, str]
) -> None:
    _add(client, sales1, cid)
    res = client.post(
        "/api/v1/contacts", json={"company_id": cid, "email": "BUYER@example.com", "source": "manual"}, headers=sales1
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CONTACT_EXISTS"
    # 不同公司可以有同一個 email（例如集團共用窗口）
    _add(client, sales1, ids["10000002"])


def test_m2_01a_create_unknown_company(client: TestClient, ids: dict[str, int], sales1: dict[str, str]) -> None:
    res = client.post(
        "/api/v1/contacts",
        json={"company_id": 999999, "email": "buyer@example.com", "source": "manual"},
        headers=sales1,
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "COMPANY_NOT_FOUND"


def test_m2_01a_locked_company_only_owner_or_manager(
    client: TestClient, cid: int, sales1: dict[str, str], sales2: dict[str, str], as_user: Headers
) -> None:
    client.post(f"/api/v1/companies/{cid}/claim", headers=sales1)
    res = client.post(
        "/api/v1/contacts", json={"company_id": cid, "email": "buyer@example.com", "source": "manual"}, headers=sales2
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "COMPANY_LOCKED"

    created = _add(client, sales1, cid)
    res = client.patch(f"/api/v1/contacts/{created['contact_id']}", json={"name": "改名"}, headers=sales2)
    assert res.json()["error"]["code"] == "COMPANY_LOCKED"

    manager = as_user("manager@example.com")
    res = client.patch(f"/api/v1/contacts/{created['contact_id']}", json={"name": "主管改"}, headers=manager)
    assert res.status_code == 200
    assert res.json()["name"] == "主管改"


# ---------- 修改 ----------
def test_m2_01a_patch_contact(client: TestClient, db: Session, cid: int, sales1: dict[str, str]) -> None:
    created = _add(client, sales1, cid, name="王小明")
    res = client.patch(
        f"/api/v1/contacts/{created['contact_id']}",
        json={"email": "Sales.Dept@example.com", "title": "業務經理", "source": "business_card"},
        headers=sales1,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["email"] == "sales.dept@example.com"
    assert body["title"] == "業務經理" and body["name"] == "王小明"  # 沒送的欄位不變
    assert body["source"] == "business_card"
    [log] = _logs(db, "contact_update")
    assert "example.com" not in f"{log.from_value}{log.to_value}{log.note}"

    # 清空職稱
    res = client.patch(f"/api/v1/contacts/{created['contact_id']}", json={"title": None}, headers=sales1)
    assert res.json()["title"] is None


def test_m2_01a_patch_rejects_duplicate_and_bad_email(client: TestClient, cid: int, sales1: dict[str, str]) -> None:
    _add(client, sales1, cid, email="a@example.com")
    second = _add(client, sales1, cid, email="b@example.com")
    url = f"/api/v1/contacts/{second['contact_id']}"
    assert (
        client.patch(url, json={"email": "A@example.com"}, headers=sales1).json()["error"]["code"] == "CONTACT_EXISTS"
    )
    assert client.patch(url, json={"email": "bad"}, headers=sales1).json()["error"]["code"] == "INVALID_EMAIL"
    assert client.patch(url, json={"source": "x"}, headers=sales1).json()["error"]["code"] == "INVALID_SOURCE"
    # 改成自己原本的 email 不算重複
    assert client.patch(url, json={"email": "B@example.com"}, headers=sales1).status_code == 200


def test_m2_01a_patch_unknown_contact(client: TestClient, ids: dict[str, int], sales1: dict[str, str]) -> None:
    res = client.patch("/api/v1/contacts/999999", json={"name": "x"}, headers=sales1)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "CONTACT_NOT_FOUND"


# ---------- 退訂（F-CASE-5）----------
def test_f_case_5_unsubscribe_marks_contact_and_company(
    client: TestClient, db: Session, cid: int, sales1: dict[str, str], sales2: dict[str, str]
) -> None:
    created = _add(client, sales1, cid)
    client.post(f"/api/v1/companies/{cid}/claim", headers=sales1)
    # 退訂一定要能生效：被別人認領的公司，其他業務也可以標記退訂
    res = client.post(
        f"/api/v1/contacts/{created['contact_id']}/unsubscribe", json={"note": "電話告知"}, headers=sales2
    )
    assert res.status_code == 200, res.text
    assert res.json()["unsubscribed"] is True

    db.expire_all()
    assert db.get(Company, cid).status == "do_not_contact"  # type: ignore[union-attr]
    assert len(_logs(db, "contact_unsubscribe")) == 1
    [status_log] = _logs(db, "status_change")
    assert status_log.to_value == "do_not_contact"

    # 重複按不會多寫紀錄，也不會出錯
    res = client.post(f"/api/v1/contacts/{created['contact_id']}/unsubscribe", headers=sales1)
    assert res.status_code == 200
    assert len(_logs(db, "contact_unsubscribe")) == 1


def test_f_case_5_unsubscribed_contact_cannot_be_resubscribed_or_change_email(
    client: TestClient, cid: int, sales1: dict[str, str]
) -> None:
    created = _add(client, sales1, cid)
    url = f"/api/v1/contacts/{created['contact_id']}"
    client.post(f"{url}/unsubscribe", headers=sales1)
    # PATCH 沒有 unsubscribed 欄位，送了也不會取消退訂
    assert client.patch(url, json={"unsubscribed": False, "name": "x"}, headers=sales1).json()["unsubscribed"] is True
    res = client.patch(url, json={"email": "new@example.com"}, headers=sales1)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CONTACT_UNSUBSCRIBED"


def test_f_case_5_unsubscribe_on_won_company_keeps_status(
    client: TestClient, db: Session, cid: int, sales1: dict[str, str]
) -> None:
    created = _add(client, sales1, cid)
    db.execute(text("UPDATE company SET status = 'won' WHERE company_id = :c"), {"c": cid})
    db.commit()
    res = client.post(f"/api/v1/contacts/{created['contact_id']}/unsubscribe", headers=sales1)
    assert res.status_code == 200
    assert res.json()["unsubscribed"] is True
    db.expire_all()
    assert db.get(Company, cid).status == "won"  # type: ignore[union-attr]


# ---------- 個資刪除（SPEC 9）----------
def _seed_mail(db: Session, company_id: int, contact_id: int) -> None:
    """直接用 SQL 建一封寄出的信和一筆事件（郵件 API 在 M2-02 之後才有）。"""
    uid = db.execute(text("SELECT user_id FROM app_user ORDER BY user_id LIMIT 1")).scalar_one()
    camp = db.execute(
        text("INSERT INTO campaign (name, owner_id) VALUES ('測試批次', :u) RETURNING campaign_id"), {"u": uid}
    ).scalar_one()
    draft = db.execute(
        text(
            "INSERT INTO email_draft (campaign_id, company_id, contact_id, subject, body_html) "
            "VALUES (:camp, :co, :ct, '主旨', '<p>內文</p>') RETURNING draft_id"
        ),
        {"camp": camp, "co": company_id, "ct": contact_id},
    ).scalar_one()
    msg = db.execute(
        text("INSERT INTO email_message (draft_id, sender_id) VALUES (:d, :u) RETURNING message_id"),
        {"d": draft, "u": uid},
    ).scalar_one()
    db.execute(text("INSERT INTO email_event (message_id, event_type) VALUES (:m, 'delivered')"), {"m": msg})
    # 另一個草稿沒寄出
    db.execute(
        text(
            "INSERT INTO email_draft (campaign_id, company_id, contact_id, subject, body_html) "
            "VALUES (:camp, :co, :ct, '主旨2', '<p>內文2</p>')"
        ),
        {"camp": camp, "co": company_id, "ct": contact_id},
    )
    db.commit()


def _count(db: Session, table: str) -> int:
    return int(db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())


def test_m2_01a_delete_contact_cascades_mail_and_logs(
    client: TestClient, db: Session, cid: int, sales1: dict[str, str], as_user: Headers
) -> None:
    keep = _add(client, sales1, cid, email="keep@example.com")
    gone = _add(client, sales1, cid, email="gone@example.com", name="要刪的人")
    _seed_mail(db, cid, int(gone["contact_id"]))
    _seed_mail(db, cid, int(keep["contact_id"]))

    manager = as_user("manager@example.com")
    res = client.request(
        "DELETE", f"/api/v1/contacts/{gone['contact_id']}", json={"reason": "客戶來信要求刪除"}, headers=manager
    )
    assert res.status_code == 204, res.text

    db.expire_all()
    emails = [r[0] for r in db.execute(text("SELECT email FROM contact"))]
    assert emails == ["keep@example.com"]
    # 被刪的人的草稿、信件、事件都不見了；另一位聯絡人的不受影響
    assert _count(db, "email_draft") == 2
    assert _count(db, "email_message") == 1
    assert _count(db, "email_event") == 1

    [log] = _logs(db, "contact_delete")
    assert log.from_value == str(gone["contact_id"])
    assert "客戶來信要求刪除" in (log.note or "")
    assert "草稿 2 封" in (log.note or "") and "寄出信件 1 封" in (log.note or "")
    # 刪除後 activity_log 裡不能留下這個人的 email 或姓名
    all_logs = " ".join(f"{x.from_value}{x.to_value}{x.note}" for x in db.scalars(select(ActivityLog)))
    assert "gone@example.com" not in all_logs and "要刪的人" not in all_logs


def test_m2_01a_delete_requires_manager_and_reason(
    client: TestClient, db: Session, cid: int, sales1: dict[str, str], as_user: Headers
) -> None:
    created = _add(client, sales1, cid)
    url = f"/api/v1/contacts/{created['contact_id']}"
    res = client.request("DELETE", url, json={"reason": "客戶要求"}, headers=sales1)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"

    manager = as_user("manager@example.com")
    res = client.request("DELETE", url, json={"reason": "  "}, headers=manager)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "DELETE_REASON_REQUIRED"
    assert client.request("DELETE", url, headers=manager).status_code == 422  # 沒有 body
    assert _count(db, "contact") == 1


def test_m2_01a_delete_unknown_contact(client: TestClient, ids: dict[str, int], as_user: Headers) -> None:
    res = client.request(
        "DELETE", "/api/v1/contacts/999999", json={"reason": "x"}, headers=as_user("admin@example.com")
    )
    assert res.status_code == 404
