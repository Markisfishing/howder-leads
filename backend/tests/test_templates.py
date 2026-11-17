"""郵件模板（M2-02a～c）與渲染（M2-03a）。"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain import template_rules as tr
from app.domain.company_rules import DomainError
from scripts.seed_templates import seed

Headers = Callable[[str], dict[str, str]]

BODY = "{{contact_name}} 您好：\n\n我是 {{sender_name}}。\n\n{{ai_paragraph}}\n\n{{unsubscribe}}"
VALUES = {"company_name": "範例公司", "contact_name": "王經理", "sender_name": "小陳"}


# ---------- domain：驗證 ----------
def test_m2_02a_validate_requires_unsubscribe() -> None:
    with pytest.raises(DomainError) as e:
        tr.validate_template("主旨", "{{contact_name}} 您好")
    assert e.value.code == "TEMPLATE_MISSING_UNSUBSCRIBE"


def test_m2_02a_validate_rejects_unknown_variable() -> None:
    with pytest.raises(DomainError) as e:
        tr.validate_template("給 {{price}}", "內文 {{unsubscribe}}")
    assert e.value.code == "TEMPLATE_UNKNOWN_VARIABLE"
    assert "price" in e.value.message


@pytest.mark.parametrize(
    ("subject", "body", "code"),
    [
        ("", "x {{unsubscribe}}", "TEMPLATE_SUBJECT_REQUIRED"),
        ("主旨", "  ", "TEMPLATE_BODY_REQUIRED"),
        ("兩行\n主旨", "x {{unsubscribe}}", "TEMPLATE_SUBJECT_MULTILINE"),
        ("{{unsubscribe}}", "x {{unsubscribe}}", "TEMPLATE_UNSUBSCRIBE_IN_SUBJECT"),
    ],
)
def test_m2_02a_validate_other_rules(subject: str, body: str, code: str) -> None:
    with pytest.raises(DomainError) as e:
        tr.validate_template(subject, body)
    assert e.value.code == code


# ---------- domain：渲染（M2-03a）----------
def test_m2_03a_render_substitutes_and_appends_unsubscribe() -> None:
    subject, body = tr.render("{{company_name}} 合作邀請", BODY, VALUES)
    assert subject == "範例公司 合作邀請"
    assert body.startswith("王經理 您好：")
    assert body.endswith(tr.UNSUBSCRIBE_TEXT)
    assert "{{" not in body
    # 選填的 ai_paragraph 沒有值，那一行拿掉，不留連續空段落
    assert "\n\n\n" not in body


def test_m2_03a_render_missing_value_raises() -> None:
    with pytest.raises(DomainError) as e:
        tr.render("x", BODY, {"sender_name": "小陳"})
    assert e.value.code == "TEMPLATE_MISSING_VALUE"
    assert "聯絡人稱呼" in e.value.message


def test_m2_03a_ensure_unsubscribe_when_removed() -> None:
    assert tr.ensure_unsubscribe("只有內文").endswith(tr.UNSUBSCRIBE_TEXT)
    once = tr.ensure_unsubscribe("內文\n\n" + tr.UNSUBSCRIBE_TEXT)
    assert once.count(tr.UNSUBSCRIBE_TEXT) == 1


def test_m2_03a_text_to_html_escapes() -> None:
    html = tr.text_to_html('第一段<script>alert("x")</script>\n第二行\n\n第二段 & 結尾')
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert html == ("<p>第一段&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;<br>第二行</p><p>第二段 &amp; 結尾</p>")


def test_m2_03a_values_are_escaped_in_html() -> None:
    _, body = tr.render("x", BODY, {**VALUES, "contact_name": "<b>王</b>"})
    assert "&lt;b&gt;" in tr.text_to_html(body)


# ---------- API ----------
@pytest.fixture
def admin(as_user: Headers) -> dict[str, str]:
    return as_user("admin@example.com")


def _create(client: TestClient, headers: dict[str, str], **extra: str) -> dict[str, object]:
    body = {"name": "邀請信", "subject": "{{company_name}} 合作邀請", "body_text": BODY, **extra}
    res = client.post("/api/v1/templates", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return dict(res.json())


def test_m2_02a_only_admin_can_write(client: TestClient, admin: dict[str, str], as_user: Headers) -> None:
    sales = as_user("sales1@example.com")
    body = {"name": "x", "subject": "x", "body_text": "x {{unsubscribe}}"}
    assert client.post("/api/v1/templates", json=body, headers=sales).status_code == 403
    created = _create(client, admin)
    assert client.put(f"/api/v1/templates/{created['template_id']}", json=body, headers=sales).status_code == 403
    assert client.post("/api/v1/templates/preview", json=body, headers=sales).status_code == 403
    # 業務可以讀（建立批次要選模板）
    assert [t["template_id"] for t in client.get("/api/v1/templates", headers=sales).json()] == [created["template_id"]]


def test_m2_02a_create_rejects_missing_unsubscribe(client: TestClient, admin: dict[str, str]) -> None:
    res = client.post("/api/v1/templates", json={"name": "x", "subject": "x", "body_text": "沒有退訂"}, headers=admin)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "TEMPLATE_MISSING_UNSUBSCRIBE"


def test_m2_02a_update_creates_new_version(client: TestClient, admin: dict[str, str]) -> None:
    v1 = _create(client, admin)
    res = client.put(
        f"/api/v1/templates/{v1['template_id']}",
        json={"name": "邀請信", "subject": "新主旨 {{company_name}}", "body_text": BODY},
        headers=admin,
    )
    assert res.status_code == 200, res.text
    v2 = res.json()
    assert v2["version"] == 2 and v2["family_id"] == v1["family_id"] and v2["template_id"] != v1["template_id"]

    # 舊版保留、停用；清單只列啟用版本
    old = client.get(f"/api/v1/templates/{v1['template_id']}", headers=admin).json()
    assert old["is_active"] is False and old["subject"] == "{{company_name}} 合作邀請"
    assert [t["template_id"] for t in client.get("/api/v1/templates", headers=admin).json()] == [v2["template_id"]]
    versions = client.get(f"/api/v1/templates/{v1['template_id']}/versions", headers=admin).json()
    assert [t["version"] for t in versions] == [2, 1]

    # 不能從舊版修改
    res = client.put(f"/api/v1/templates/{v1['template_id']}", json={**v2, "name": "x"}, headers=admin)
    assert res.json()["error"]["code"] == "TEMPLATE_NOT_ACTIVE"


def test_m2_02a_archive(client: TestClient, admin: dict[str, str]) -> None:
    t = _create(client, admin)
    assert client.post(f"/api/v1/templates/{t['template_id']}/archive", headers=admin).json()["is_active"] is False
    assert client.get("/api/v1/templates", headers=admin).json() == []


def test_m2_02b_preview_uses_fake_data(client: TestClient, admin: dict[str, str]) -> None:
    res = client.post(
        "/api/v1/templates/preview", json={"subject": "{{company_name}} 邀請", "body_text": BODY}, headers=admin
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["subject"] == "範例科技股份有限公司 邀請"
    assert body["body_html"].startswith("<p>王經理 您好：</p>")
    assert tr.UNSUBSCRIBE_TEXT in body["body_text"]


def test_m2_02a_variables_list(client: TestClient, admin: dict[str, str]) -> None:
    names = {v["name"] for v in client.get("/api/v1/templates/variables", headers=admin).json()}
    assert {"company_name", "contact_name", "sender_name", "unsubscribe"} <= names


def test_m2_02c_seed_is_idempotent(db: Session) -> None:
    assert seed(db) is True
    assert seed(db) is False
