"""邀請信流程整合測試：建立批次 → worker 產生草稿 → 審核 → 寄出（M2-03～M2-08）。

全部用 sandbox／假的寄信實作，不呼叫真的 Graph（CLAUDE.md 第 6 節第 4 點）。email 都是 @example.com。
"""

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import get_engine
from app.domain import template_rules
from app.models import Company, EmailDraft, EmailMessage, Job
from app.services.llm import FakeLlmClient
from app.services.mailer import MailAuthError, MailSendError, OutgoingMail, SandboxMailer, SendResult
from app.services.site_fetcher import FakeSiteFetcher
from app.workers.runner import WorkerDeps, run_until_idle
from tests.factories import csv_bytes

Headers = Callable[[str], dict[str, str]]
TEMPLATE_BODY = "{{contact_name}} 您好：\n\n我是 {{sender_name}}，想和 {{company_name}} 介紹端子台。\n\n{{unsubscribe}}"


@dataclass
class FakeMailer:
    """記錄寄出的信；fail_with 可以讓它丟錯。"""

    sent: list[OutgoingMail] = field(default_factory=list)
    fail_with: Exception | None = None

    def send(self, mail: OutgoingMail) -> SendResult:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append(mail)
        return SendResult(graph_message_id=f"msg-{mail.draft_id}", conversation_id=f"conv-{mail.draft_id}")


@dataclass
class World:
    client: TestClient
    app: FastAPI
    db: Session
    sales1: dict[str, str]
    sales2: dict[str, str]
    manager: dict[str, str]
    ids: dict[str, int]  # 統編 → company_id
    contacts: dict[int, int]  # company_id → contact_id
    template_id: int
    settings: Settings
    mailer: FakeMailer
    clock: list[datetime]

    def worker(self, *, advance: timedelta = timedelta(0)) -> int:
        self.clock[0] = self.clock[0] + advance
        # LLM 一律用假的：沒放回覆的 FakeLlmClient 會直接失敗，不會連本機 Ollama
        deps = WorkerDeps(
            settings=self.settings,
            mailer=self.mailer,
            now=lambda: self.clock[0],
            llm=FakeLlmClient(),
            site_fetcher=FakeSiteFetcher(),
        )
        n = run_until_idle(sessionmaker(bind=get_engine(), expire_on_commit=False), deps)
        self.db.expire_all()
        return n

    def create(self, company_ids: list[int], headers: dict[str, str] | None = None, **extra: object) -> dict:  # type: ignore[type-arg]
        body = {
            "name": "測試批次",
            "template_id": self.template_id,
            "targets": [{"company_id": c, "contact_id": self.contacts.get(c)} for c in company_ids],
            **extra,
        }
        res = self.client.post("/api/v1/campaigns", json=body, headers=headers or self.sales1)
        assert res.status_code == 201, res.text
        return dict(res.json())

    def drafts(self, campaign_id: int) -> list[dict]:  # type: ignore[type-arg]
        return list(self.client.get(f"/api/v1/campaigns/{campaign_id}/drafts", headers=self.sales1).json()["items"])

    def status(self, company_id: int) -> str:
        self.db.expire_all()
        return self.db.get(Company, company_id).status  # type: ignore[union-attr]


@pytest.fixture
def world(client: TestClient, db: Session, as_user: Headers) -> Iterator[World]:
    admin = as_user("admin@example.com")
    batch = client.post("/api/v1/imports", files={"file": ("a.csv", csv_bytes(), "text/csv")}, headers=admin).json()
    client.post(f"/api/v1/imports/{batch['batch_id']}/commit", headers=admin)
    ids = {c["tax_id"]: c["company_id"] for c in client.get("/api/v1/companies", headers=admin).json()["items"]}
    sales1, sales2, manager = (
        as_user("sales1@example.com"),
        as_user("sales2@example.com"),
        as_user("manager@example.com"),
    )
    # 前三家通過審核，第四家留在待審
    approved = [ids["10000001"], ids["10000002"], ids["10000003"]]
    assert client.post(
        "/api/v1/reviews", json={"company_ids": approved, "decision": "approved"}, headers=sales1
    ).is_success
    contacts = {}
    for i, cid in enumerate([*approved, ids["10000004"]]):
        res = client.post(
            "/api/v1/contacts",
            json={"company_id": cid, "email": f"buyer{i}@example.com", "source": "website", "name": f"窗口{i}"},
            headers=admin,
        )
        contacts[cid] = res.json()["contact_id"]
    template_id = client.post(
        "/api/v1/templates",
        json={"name": "邀請信", "subject": "{{company_name}} 合作邀請", "body_text": TEMPLATE_BODY},
        headers=admin,
    ).json()["template_id"]
    # 排程間隔設很短，測試不用等
    settings = get_settings().model_copy(update={"send_per_minute": 6000, "daily_send_limit": 50})
    app: FastAPI = client.app  # type: ignore[assignment]
    app.dependency_overrides[get_settings] = lambda: settings
    w = World(
        client=client,
        app=app,
        db=db,
        sales1=sales1,
        sales2=sales2,
        manager=manager,
        ids=ids,
        contacts=contacts,
        template_id=template_id,
        settings=settings,
        mailer=FakeMailer(),
        clock=[datetime.now(UTC) + timedelta(minutes=1)],
    )
    w.worker()  # 匯入確認會排 fetch_site 工作（M4-08c）：先清掉，讓各測試從乾淨的佇列開始
    yield w
    app.dependency_overrides.clear()


# ---------- 建立批次（F-MAIL-1、M2-03b）----------
def test_f_mail_1_create_campaign_returns_job_and_marks_drafted(world: World) -> None:
    a, b = world.ids["10000001"], world.ids["10000002"]
    out = world.create([a, b])
    assert out["job_id"] > 0
    assert out["excluded"] == []
    assert out["campaign"]["status"] == "generating"
    assert out["campaign"]["progress"]["generating"] == 2
    assert world.status(a) == "drafted"
    assert world.db.scalar(select(func.count()).select_from(Job).where(Job.kind == "generate_drafts")) == 1


def test_m2_03b_missing_contact_id_uses_default_contact(world: World) -> None:
    """bug（M2-13 發現）：API 允許 contact_id 不填，應該用該公司第一位沒退訂的聯絡人，不是判成「沒有聯絡人」。"""
    a = world.ids["10000001"]
    res = world.client.post(
        "/api/v1/campaigns",
        json={"name": "x", "template_id": world.template_id, "targets": [{"company_id": a}]},
        headers=world.sales1,
    )
    assert res.status_code == 201, res.text
    world.worker()
    assert [d["contact_id"] for d in world.drafts(res.json()["campaign"]["campaign_id"])] == [world.contacts[a]]


def test_f_mail_1_pending_company_is_excluded_with_reason(world: World) -> None:
    out = world.create([world.ids["10000001"], world.ids["10000004"]])
    assert [(e["company_id"], e["reasons"]) for e in out["excluded"]] == [(world.ids["10000004"], ["NOT_APPROVED"])]
    assert out["campaign"]["progress"]["total"] == 1


def test_f_mail_1_all_excluded_is_rejected(world: World) -> None:
    res = world.client.post(
        "/api/v1/campaigns",
        json={"name": "x", "template_id": world.template_id, "targets": [{"company_id": world.ids["10000004"]}]},
        headers=world.sales1,
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "NO_ELIGIBLE_TARGETS"


def test_f_mail_2_unknown_gen_mode_rejected(world: World) -> None:
    res = world.client.post(
        "/api/v1/campaigns",
        json={
            "name": "x",
            "template_id": world.template_id,
            "gen_mode": "magic",
            "targets": [{"company_id": world.ids["10000001"], "contact_id": world.contacts[world.ids["10000001"]]}],
        },
        headers=world.sales1,
    )
    assert res.status_code == 422  # AI 模式在 M4-06 開放；沒有的模式仍然擋下


def test_f_mail_7_unsubscribed_and_locked_are_excluded(world: World) -> None:
    a, b, c = world.ids["10000001"], world.ids["10000002"], world.ids["10000003"]
    world.client.post(f"/api/v1/contacts/{world.contacts[a]}/unsubscribe", headers=world.sales1)
    world.client.post(f"/api/v1/companies/{b}/claim", headers=world.sales2)
    out = world.create([a, b, c])
    reasons = {e["company_id"]: e["reasons"] for e in out["excluded"]}
    assert reasons[a] == ["DO_NOT_CONTACT", "UNSUBSCRIBED"]
    assert reasons[b] == ["LOCKED_BY_OTHER"]
    assert c not in reasons


def test_f_mail_7_candidates_show_reasons(world: World) -> None:
    world.client.post(f"/api/v1/companies/{world.ids['10000002']}/claim", headers=world.sales2)
    rows = {r["company_id"]: r for r in world.client.get("/api/v1/campaigns/candidates", headers=world.sales1).json()}
    assert set(rows) == {world.ids["10000001"], world.ids["10000002"], world.ids["10000003"]}  # 只有已通過
    assert rows[world.ids["10000002"]]["reasons"] == ["LOCKED_BY_OTHER"]
    assert rows[world.ids["10000001"]]["default_contact_id"] == world.contacts[world.ids["10000001"]]


def _cand_ids(world: World, query: str = "") -> set[int]:
    res = world.client.get(f"/api/v1/campaigns/candidates{query}", headers=world.sales1)
    assert res.status_code == 200, res.text
    return {r["company_id"] for r in res.json()}


def test_m3_16_candidates_search_by_name_or_tax_id(world: World) -> None:
    auto, motor = world.ids["10000001"], world.ids["10000002"]
    assert _cand_ids(world, "?q=自動化") == {auto}
    assert _cand_ids(world, "?q=10000002") == {motor}
    assert _cand_ids(world, "?q=不存在的公司") == set()
    assert _cand_ids(world, "?q=%20%20") == {auto, motor, world.ids["10000003"]}  # 只有空白等於沒有條件


def test_m3_16_candidates_filter_by_industry_and_stars(world: World) -> None:
    rows = world.client.get("/api/v1/companies", headers=world.sales1).json()["items"]
    auto = next(r for r in rows if r["tax_id"] == "10000001")
    assert _cand_ids(world, f"?industry_id={auto['industry_id']}") == {auto["company_id"]}
    assert _cand_ids(world, f"?stars={auto['stars']}") == {auto["company_id"]}
    # 篩選只縮小範圍：未通過審核的公司（第 4 家）不會因為符合條件而出現
    assert world.ids["10000004"] not in _cand_ids(world, "?q=測試")


def test_m3_16_candidates_filters_combine_and_keep_reasons(world: World) -> None:
    motor = world.ids["10000002"]
    world.client.post(f"/api/v1/companies/{motor}/claim", headers=world.sales2)
    res = world.client.get("/api/v1/campaigns/candidates?q=電機", headers=world.sales1).json()
    assert [r["company_id"] for r in res] == [motor]
    assert res[0]["reasons"] == ["LOCKED_BY_OTHER"]  # 篩出來的仍然標示不能寄的原因
    assert _cand_ids(world, "?q=電機&industry_id=9999") == set()


def test_m2_03b_contact_must_belong_to_company(world: World) -> None:
    a, b = world.ids["10000001"], world.ids["10000002"]
    res = world.client.post(
        "/api/v1/campaigns",
        json={
            "name": "x",
            "template_id": world.template_id,
            "targets": [{"company_id": a, "contact_id": world.contacts[b]}],
        },
        headers=world.sales1,
    )
    assert res.json()["error"]["code"] == "NO_ELIGIBLE_TARGETS"


# ---------- 產生草稿（F-MAIL-3、M2-03c）----------
def test_f_mail_3_worker_generates_drafts(world: World) -> None:
    out = world.create([world.ids["10000001"], world.ids["10000002"]])
    cid = out["campaign"]["campaign_id"]
    assert world.worker() == 1
    drafts = world.drafts(cid)
    assert [d["status"] for d in drafts] == ["pending_review", "pending_review"]
    first = drafts[0]
    assert first["subject"] == "測試自動化股份有限公司 合作邀請"
    assert first["body_text"].startswith("窗口0 您好")
    assert first["body_text"].endswith(template_rules.UNSUBSCRIBE_TEXT)
    row = world.db.get(EmailDraft, first["draft_id"])
    assert row is not None and row.ai_original == row.body_text  # F-MAIL-8 比對用
    camp = world.client.get(f"/api/v1/campaigns/{cid}", headers=world.sales1).json()
    assert camp["status"] == "reviewing" and camp["progress"]["pending_review"] == 2


def test_f_mail_3_one_failure_does_not_stop_others(world: World) -> None:
    admin = {"X-Dev-User": "admin@example.com"}
    # 模板用到 {{industry}}；手動加入、沒有產業的公司會產生失敗，其他封照常
    tpl = world.client.put(
        f"/api/v1/templates/{world.template_id}",
        json={"name": "邀請信", "subject": "{{industry}} 的 {{company_name}}", "body_text": TEMPLATE_BODY},
        headers=admin,
    ).json()
    manual = world.client.post("/api/v1/companies", json={"tax_id": "10000099", "name": "沒有產業公司"}, headers=admin)
    mid = manual.json()["company_id"]
    world.client.post("/api/v1/reviews", json={"company_ids": [mid], "decision": "approved"}, headers=admin)
    ct = world.client.post(
        "/api/v1/contacts", json={"company_id": mid, "email": "x@example.com", "source": "manual"}, headers=admin
    ).json()
    world.contacts[mid] = ct["contact_id"]
    world.template_id = tpl["template_id"]
    out = world.create([world.ids["10000001"], mid])
    world.worker()
    statuses = {d["company_id"]: (d["status"], d["last_error"]) for d in world.drafts(out["campaign"]["campaign_id"])}
    assert statuses[world.ids["10000001"]] == ("pending_review", None)
    assert statuses[mid] == ("failed", "TEMPLATE_MISSING_VALUE")


# ---------- 預覽佇列（F-MAIL-4、M2-05）----------
def _generated(world: World, n: int = 2) -> tuple[int, list[dict]]:  # type: ignore[type-arg]
    targets = [world.ids["10000001"], world.ids["10000002"], world.ids["10000003"]][:n]
    cid = world.create(targets)["campaign"]["campaign_id"]
    world.worker()
    return cid, world.drafts(cid)


def test_f_mail_4_edit_and_approve_records_edit_ratio(world: World) -> None:
    _, drafts = _generated(world, 1)
    d = drafts[0]
    url = f"/api/v1/drafts/{d['draft_id']}"
    res = world.client.patch(url, json={"body_text": "窗口0 您好：\n\n我們改寫了整段內容。"}, headers=world.sales1)
    assert res.status_code == 200, res.text
    assert res.json()["body_text"].endswith(template_rules.UNSUBSCRIBE_TEXT)  # 刪掉退訂說明也會補回
    approved = world.client.post(f"{url}/approve", headers=world.sales1).json()
    assert approved["status"] == "approved"
    assert Decimal(str(approved["edit_ratio"])) > 0  # F-MAIL-8
    assert world.status(d["company_id"]) == "draft_approved"
    # 已核准不能直接改
    assert world.client.patch(url, json={"subject": "x"}, headers=world.sales1).json()["error"]["code"] == (
        "DRAFT_NOT_EDITABLE"
    )


def test_f_mail_8_unedited_draft_ratio_zero(world: World) -> None:
    _, drafts = _generated(world, 1)
    res = world.client.post(f"/api/v1/drafts/{drafts[0]['draft_id']}/approve", headers=world.sales1).json()
    assert Decimal(str(res["edit_ratio"])) == 0


def test_f_mail_4_approve_all_requires_confirm(world: World) -> None:
    cid, _ = _generated(world, 2)
    url = f"/api/v1/campaigns/{cid}/approve-all"
    res = world.client.post(url, json={}, headers=world.sales1)
    assert res.json()["error"]["code"] == "CONFIRM_REQUIRED"
    res = world.client.post(url, json={"confirm": True}, headers=world.sales1)
    assert res.json()["progress"]["approved"] == 2


def test_f_mail_4_discard_returns_company_to_approved(world: World) -> None:
    _, drafts = _generated(world, 1)
    d = drafts[0]
    world.client.post(f"/api/v1/drafts/{d['draft_id']}/approve", headers=world.sales1)
    res = world.client.post(f"/api/v1/drafts/{d['draft_id']}/discard", headers=world.sales1)
    assert res.json()["status"] == "discarded"
    assert world.status(d["company_id"]) == "approved"


def test_f_mail_4_unapprove_and_regenerate(world: World) -> None:
    _, drafts = _generated(world, 1)
    url = f"/api/v1/drafts/{drafts[0]['draft_id']}"
    world.client.post(f"{url}/approve", headers=world.sales1)
    assert world.client.post(f"{url}/regenerate", headers=world.sales1).json()["error"]["code"] == "DRAFT_NOT_EDITABLE"
    assert world.client.post(f"{url}/unapprove", headers=world.sales1).json()["status"] == "pending_review"
    assert world.status(drafts[0]["company_id"]) == "drafted"
    res = world.client.post(f"{url}/regenerate", headers=world.sales1)
    assert res.status_code == 202
    world.worker()
    assert world.drafts(drafts[0]["campaign_id"])[0]["status"] == "pending_review"


def test_m2_05a_other_sales_cannot_see_or_review(world: World) -> None:
    cid, drafts = _generated(world, 1)
    assert world.client.get(f"/api/v1/campaigns/{cid}", headers=world.sales2).status_code == 404
    res = world.client.post(f"/api/v1/drafts/{drafts[0]['draft_id']}/approve", headers=world.sales2)
    assert res.status_code == 404
    # 主管可以看、可以審
    assert world.client.get(f"/api/v1/campaigns/{cid}", headers=world.manager).status_code == 200
    assert (
        world.client.post(f"/api/v1/drafts/{drafts[0]['draft_id']}/approve", headers=world.manager).status_code == 200
    )


# ---------- 寄出（F-MAIL-5、F-MAIL-6、M2-07）----------
def _approved(world: World, n: int = 2) -> tuple[int, list[dict]]:  # type: ignore[type-arg]
    cid, drafts = _generated(world, n)
    world.client.post(f"/api/v1/campaigns/{cid}/approve-all", json={"confirm": True}, headers=world.sales1)
    return cid, drafts


def _campaign_status(world: World, cid: int) -> str:
    return str(world.client.get(f"/api/v1/campaigns/{cid}", headers=world.sales1).json()["status"])


def test_m2_16_all_reviewed_becomes_ready(world: World) -> None:
    cid, drafts = _generated(world, 2)
    first = f"/api/v1/drafts/{drafts[0]['draft_id']}"
    world.client.post(f"{first}/approve", headers=world.sales1)
    assert _campaign_status(world, cid) == "reviewing"  # 還有一封待審核
    world.client.post(f"/api/v1/drafts/{drafts[1]['draft_id']}/discard", headers=world.sales1)
    assert _campaign_status(world, cid) == "ready"  # 都處理完、還沒按寄出 → 待寄出
    world.client.post(f"{first}/unapprove", headers=world.sales1)
    assert _campaign_status(world, cid) == "reviewing"  # 取消核准退回待審核


def test_m2_16_ready_then_send_becomes_scheduled(world: World) -> None:
    cid, _ = _approved(world, 2)
    assert _campaign_status(world, cid) == "ready"
    res = world.client.post(f"/api/v1/campaigns/{cid}/send", json={}, headers=world.sales1)
    assert res.json()["campaign"]["status"] == "scheduled"


def _count(world: World, model: type) -> int:
    world.db.expire_all()
    return int(world.db.scalar(select(func.count()).select_from(model)) or 0)


def test_f_mail_6_full_flow_sends_approved_drafts(world: World) -> None:
    cid, drafts = _approved(world, 2)
    res = world.client.post(f"/api/v1/campaigns/{cid}/send", json={}, headers=world.sales1)
    assert res.status_code == 200, res.text
    assert res.json()["scheduled"] == 2
    assert _count(world, EmailMessage) == 0  # 按寄出只排進佇列，worker 才寄
    world.worker()
    assert [m.to_email for m in world.mailer.sent] == ["buyer0@example.com", "buyer1@example.com"]
    assert _count(world, EmailMessage) == 2
    for d in world.drafts(cid):
        assert d["status"] == "sent"
        assert world.status(d["company_id"]) == "sent"
    camp = world.client.get(f"/api/v1/campaigns/{cid}", headers=world.sales1).json()
    assert camp["status"] == "done" and camp["progress"]["sent"] == 2
    kpi = world.client.get("/api/v1/metrics/kpis", headers=world.sales1).json()
    assert kpi["sent_7d"] == 2  # M2-12


def test_f_mail_5_nothing_approved_cannot_send(world: World) -> None:
    cid, _ = _generated(world, 1)
    res = world.client.post(f"/api/v1/campaigns/{cid}/send", json={}, headers=world.sales1)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "NOTHING_TO_SEND"


def test_f_mail_5_worker_never_sends_unapproved_draft(world: World) -> None:
    """就算佇列裡有一筆指向未核准草稿的寄送工作，worker 也不會寄。"""
    _, drafts = _generated(world, 1)
    world.db.add(Job(kind="send_email", payload={"draft_id": drafts[0]["draft_id"]}))
    world.db.commit()
    world.worker()
    assert world.mailer.sent == []
    assert _count(world, EmailMessage) == 0


def test_f_mail_5_unapprove_after_schedule_cancels_send(world: World) -> None:
    cid, drafts = _approved(world, 1)
    world.client.post(f"/api/v1/campaigns/{cid}/send", json={}, headers=world.sales1)
    world.client.post(f"/api/v1/drafts/{drafts[0]['draft_id']}/unapprove", headers=world.sales1)
    world.worker()
    assert world.mailer.sent == []


def test_m2_07d_only_owner_can_send(world: World) -> None:
    cid, _ = _approved(world, 1)
    res = world.client.post(f"/api/v1/campaigns/{cid}/send", json={}, headers=world.manager)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "SEND_OWNER_ONLY"


def test_m2_04b_guard_rechecked_before_send(world: World) -> None:
    """排程後聯絡人退訂：worker 寄出前再查一次，不寄並標成失敗。"""
    cid, drafts = _approved(world, 1)
    world.client.post(f"/api/v1/campaigns/{cid}/send", json={}, headers=world.sales1)
    world.client.post(f"/api/v1/contacts/{world.contacts[drafts[0]['company_id']]}/unsubscribe", headers=world.sales2)
    world.worker()
    assert world.mailer.sent == []
    d = world.drafts(cid)[0]
    assert d["status"] == "failed" and d["last_error"].startswith("GUARD:")


def test_m2_04b_guard_checked_when_scheduling(world: World) -> None:
    cid, drafts = _approved(world, 2)
    world.client.post(f"/api/v1/companies/{drafts[0]['company_id']}/claim", headers=world.sales2)
    res = world.client.post(f"/api/v1/campaigns/{cid}/send", json={}, headers=world.sales1).json()
    assert res["scheduled"] == 1
    assert res["blocked"][0]["reasons"] == ["LOCKED_BY_OTHER"]


def test_f_mail_7_recently_sent_company_not_sent_again(world: World) -> None:
    cid, drafts = _approved(world, 1)
    world.client.post(f"/api/v1/campaigns/{cid}/send", json={}, headers=world.sales1)
    world.worker()
    company = drafts[0]["company_id"]
    # 同一家公司丟回 approved 再建新批次 → 14 天內寄過，被排除
    world.db.execute(text("UPDATE company SET status = 'approved' WHERE company_id = :c"), {"c": company})
    world.db.commit()
    res = world.client.post(
        "/api/v1/campaigns",
        json={
            "name": "x",
            "template_id": world.template_id,
            "targets": [{"company_id": company, "contact_id": world.contacts[company]}],
        },
        headers=world.sales1,
    )
    assert res.json()["error"]["code"] == "NO_ELIGIBLE_TARGETS"
    assert "14 天內已經寄過" in res.json()["error"]["message"]


def test_f_mail_6_daily_limit_moves_extra_to_next_day(world: World) -> None:
    world.settings = world.settings.model_copy(update={"daily_send_limit": 2})
    world.app.dependency_overrides[get_settings] = lambda: world.settings
    cid, _ = _approved(world, 3)
    world.client.post(f"/api/v1/campaigns/{cid}/send", json={}, headers=world.sales1)
    world.worker()
    assert len(world.mailer.sent) == 2
    third = [d for d in world.drafts(cid) if d["status"] == "approved"]
    assert len(third) == 1 and third[0]["scheduled_at"] is not None
    world.worker(advance=timedelta(days=1, hours=12))  # 隔天
    assert len(world.mailer.sent) == 3


def test_f_mail_6_schedule_in_future(world: World) -> None:
    cid, _ = _approved(world, 1)
    at = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    res = world.client.post(f"/api/v1/campaigns/{cid}/send", json={"scheduled_at": at}, headers=world.sales1).json()
    assert res["campaign"]["status"] == "scheduled"
    world.worker()
    assert world.mailer.sent == []
    world.worker(advance=timedelta(days=2, minutes=5))
    assert len(world.mailer.sent) == 1


def test_m2_07e_retries_then_marks_failed(world: World) -> None:
    cid, drafts = _approved(world, 1)
    world.mailer.fail_with = MailSendError("GRAPH_HTTP_503")
    world.client.post(f"/api/v1/campaigns/{cid}/send", json={}, headers=world.sales1)
    for _ in range(3):  # 指數退避：每次往後推一段時間再跑
        world.worker(advance=timedelta(minutes=10))
    d = world.drafts(cid)[0]
    assert d["status"] == "failed"
    assert d["last_error"] == "GRAPH_HTTP_503"
    assert d["send_attempts"] == 3
    assert world.status(drafts[0]["company_id"]) == "drafted"
    camp = world.client.get(f"/api/v1/campaigns/{cid}", headers=world.sales1).json()
    assert camp["progress"]["failed"] == 1


def test_m2_07c_auth_error_pauses_sending(world: World) -> None:
    cid, _ = _approved(world, 1)
    world.mailer.fail_with = MailAuthError()
    world.client.post(f"/api/v1/campaigns/{cid}/send", json={}, headers=world.sales1)
    world.worker()
    d = world.drafts(cid)[0]
    assert d["status"] == "approved" and d["scheduled_at"] is None
    assert d["last_error"] == "MAIL_AUTH_REQUIRED"


def test_m2_07a_sandbox_log_has_no_mail_body(caplog: pytest.LogCaptureFixture) -> None:
    mail = OutgoingMail(
        draft_id=1, sender_user_id=1, to_email="buyer@example.com", subject="機密主旨", body_html="<p>機密內文</p>"
    )
    with caplog.at_level(logging.INFO):
        result = SandboxMailer().send(mail)
    assert result.graph_message_id and result.graph_message_id.startswith("sandbox-")
    assert "機密" not in caplog.text
    assert "buyer@example.com" not in caplog.text
    assert "機密" not in repr(mail)
