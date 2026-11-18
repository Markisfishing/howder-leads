"""AI 產生草稿（M4-06c、M4-06i、M4-06j、F-MAIL-2、F-MAIL-3、F-MAIL-8）。

LLM 一律用 FakeLlmClient：自動化測試不連本機 Ollama 也不連 Claude（CLAUDE.md 第 6 節第 4 點）。
"""

import json

import pytest
from sqlalchemy.orm import sessionmaker

from app.db import get_engine
from app.domain import draft_rules, template_rules
from app.models import EmailDraft
from app.services import ai_writer
from app.services.llm import FakeLlmClient, LlmError, LlmRequest
from app.workers.runner import WorkerDeps, run_until_idle
from tests.test_campaigns import World, world  # noqa: F401  （world 是 fixture）

PARAGRAPH = "我們注意到貴公司在工業自動化領域有控制箱與配電設備的需求，厚達電子專注於端子台製造，期待有機會交流。"
AI_BODY = (
    "採購負責人 您好：\n\n我是厚達電子的業務，看到貴公司的產品與控制箱相關，想和您交流端子台的應用。"
    "若方便，歡迎回信告知合適的聯絡時間。\n\n業務敬上"
)
AI_TEMPLATE_BODY = "{{contact_name}} 您好：\n\n{{ai_paragraph}}\n\n{{sender_name}} 敬上\n\n{{unsubscribe}}"


def _para(text: str = PARAGRAPH) -> str:
    return json.dumps({"ai_paragraph": text}, ensure_ascii=False)


def _mail(subject: str = "與貴公司交流端子台應用", body: str = AI_BODY) -> str:
    return json.dumps({"subject": subject, "body_text": body}, ensure_ascii=False)


def _run(world: World, llm: FakeLlmClient) -> int:  # noqa: F811
    deps = WorkerDeps(settings=world.settings, mailer=world.mailer, now=lambda: world.clock[0], llm=llm)
    n = run_until_idle(sessionmaker(bind=get_engine(), expire_on_commit=False), deps)
    world.db.expire_all()
    return n


def _ai_template(world: World) -> int:  # noqa: F811
    res = world.client.post(
        "/api/v1/templates",
        json={"name": "AI 邀請信", "subject": "{{company_name}} 合作邀請", "body_text": AI_TEMPLATE_BODY},
        headers={"X-Dev-User": "admin@example.com"},
    )
    assert res.status_code in (200, 201), res.text
    return int(res.json()["template_id"])


def _create(world: World, mode: str, company_ids: list[int], template_id: int | None = None) -> int:  # noqa: F811
    out = world.create(company_ids, gen_mode=mode, template_id=template_id or world.template_id)
    return int(out["campaign"]["campaign_id"])


def _draft(world: World, campaign_id: int, index: int = 0) -> EmailDraft:  # noqa: F811
    return world.db.query(EmailDraft).filter_by(campaign_id=campaign_id).order_by(EmailDraft.draft_id).all()[index]


# ---------- template_ai（M4-06c）----------
def test_m4_06c_template_ai_inserts_paragraph_and_records_generation_info(world: World) -> None:  # noqa: F811
    cid = _create(world, "template_ai", [world.ids["10000001"]], _ai_template(world))
    llm = FakeLlmClient([_para()])
    assert _run(world, llm) >= 1
    d = _draft(world, cid)
    assert d.status == "pending_review"
    assert PARAGRAPH in d.body_text
    assert d.body_text.startswith("窗口0 您好")
    assert d.body_text.endswith(template_rules.UNSUBSCRIBE_TEXT)
    assert d.subject == "測試自動化股份有限公司 合作邀請"
    assert (d.gen_provider, d.gen_model, d.prompt_version) == ("fake", "fake-model", "invite_v1")
    assert d.ai_original == d.body_text  # F-MAIL-8
    # 送給 AI 的只有公司層級資料，沒有聯絡人 email
    sent = llm.requests[0]
    assert "測試自動化股份有限公司" in sent.user
    assert "@example.com" not in sent.user
    assert "不可以捏造" in sent.system  # 不捏造實績、價格、認證、交期（CLAUDE.md 第 6 節第 6 點）


def test_m4_06c_template_ai_requires_ai_paragraph_variable(world: World) -> None:  # noqa: F811
    cid = _create(world, "template_ai", [world.ids["10000001"]])  # 預設模板沒有 {{ai_paragraph}}
    llm = FakeLlmClient([_para()])
    _run(world, llm)
    d = _draft(world, cid)
    assert (d.status, d.last_error) == ("failed", "TEMPLATE_NO_AI_PARAGRAPH")
    assert llm.requests == []  # 模板不合就不浪費一次 LLM 呼叫


def test_m4_06c_template_only_has_no_generation_info(world: World) -> None:  # noqa: F811
    cid = _create(world, "template_only", [world.ids["10000001"]])
    assert world.worker() >= 1
    d = _draft(world, cid)
    assert d.status == "pending_review"
    assert (d.gen_provider, d.gen_model, d.prompt_version) == (None, None, None)


def test_m4_06c_prompt_file_is_versioned_and_forbids_fabrication() -> None:
    for mode in ("template_ai", "full_ai"):
        system = ai_writer.load_system_prompt(ai_writer.PROMPT_VERSION, mode)
        assert "繁體中文" in system and "捏造" in system and "價格" in system and "認證" in system and "交期" in system
    with pytest.raises(LlmError) as e:
        ai_writer.load_system_prompt(ai_writer.PROMPT_VERSION, "no_such_mode")
    assert e.value.code == "PROMPT_NOT_FOUND"


# ---------- full_ai（M4-06i）----------
def test_m4_06i_full_ai_writes_subject_body_and_system_adds_unsubscribe(world: World) -> None:  # noqa: F811
    cid = _create(world, "full_ai", [world.ids["10000001"]])
    llm = FakeLlmClient([_mail()])
    _run(world, llm)
    d = _draft(world, cid)
    assert d.status == "pending_review"
    assert d.subject == "與貴公司交流端子台應用"
    assert d.body_text.startswith(AI_BODY)
    assert d.body_text.endswith(template_rules.UNSUBSCRIBE_TEXT)  # AI 沒寫，系統補
    assert d.ai_original == d.body_text
    assert d.prompt_version == "invite_v1"
    assert "窗口0" in llm.requests[0].user and "@example.com" not in llm.requests[0].user


def test_m4_06i_full_ai_does_not_duplicate_unsubscribe_text(world: World) -> None:  # noqa: F811
    cid = _create(world, "full_ai", [world.ids["10000001"]])
    _run(world, FakeLlmClient([_mail(body=AI_BODY + "\n\n" + template_rules.UNSUBSCRIBE_TEXT)]))
    assert _draft(world, cid).body_text.count(template_rules.UNSUBSCRIBE_TEXT) == 1


# ---------- 失敗與重試（M4-06j）----------
def test_m4_06j_bad_json_is_retried_once_then_succeeds(world: World) -> None:  # noqa: F811
    cid = _create(world, "full_ai", [world.ids["10000001"]])
    llm = FakeLlmClient(["這不是 JSON", _mail()])
    _run(world, llm)
    assert _draft(world, cid).status == "pending_review"
    assert len(llm.requests) == 2


def test_m4_06j_simplified_chinese_is_retried_then_fails_with_code(world: World) -> None:  # noqa: F811
    cid = _create(world, "full_ai", [world.ids["10000001"]])
    simplified = _mail(
        subject="合作邀请", body=AI_BODY.replace("交流", "交流").replace("應用", "应用") + "我们期待与您联络。"
    )
    llm = FakeLlmClient([simplified, simplified])
    _run(world, llm)
    d = _draft(world, cid)
    assert (d.status, d.last_error) == ("failed", "AI_SIMPLIFIED_CHINESE")
    assert len(llm.requests) == 2  # 重試一次就停


def test_m4_06j_timeout_is_retried_then_fails(world: World) -> None:  # noqa: F811
    cid = _create(world, "template_ai", [world.ids["10000001"]], _ai_template(world))
    llm = FakeLlmClient([LlmError("LLM_TIMEOUT", retryable=True), LlmError("LLM_TIMEOUT", retryable=True)])
    _run(world, llm)
    d = _draft(world, cid)
    assert (d.status, d.last_error) == ("failed", "LLM_TIMEOUT")
    assert (d.gen_provider, d.gen_model) == (None, None)


def test_m4_06j_non_retryable_error_does_not_retry(world: World) -> None:  # noqa: F811
    cid = _create(world, "template_ai", [world.ids["10000001"]], _ai_template(world))
    llm = FakeLlmClient([LlmError("LLM_BAD_REQUEST", retryable=False), _para()])
    _run(world, llm)
    assert (_draft(world, cid).status, _draft(world, cid).last_error) == ("failed", "LLM_BAD_REQUEST")
    assert len(llm.requests) == 1


def test_m4_06j_one_failure_does_not_stop_others_and_runs_concurrently(world: World) -> None:  # noqa: F811
    a, b, c = world.ids["10000001"], world.ids["10000002"], world.ids["10000003"]
    cid = _create(world, "template_ai", [a, b, c], _ai_template(world))

    def reply(request: LlmRequest) -> str:
        if "測試電機" in request.user:
            raise LlmError("LLM_UNAVAILABLE", retryable=False)
        return _para()

    world.settings = world.settings.model_copy(update={"llm_concurrency": 3})
    _run(world, FakeLlmClient(reply))
    statuses = {d.company_id: d.status for d in world.db.query(EmailDraft).filter_by(campaign_id=cid)}
    assert statuses == {a: "pending_review", b: "failed", c: "pending_review"}
    assert {d.company_id: d.last_error for d in world.db.query(EmailDraft).filter_by(campaign_id=cid)}[b] == (
        "LLM_UNAVAILABLE"
    )


def test_m4_06j_regenerate_failed_ai_draft_uses_same_path(world: World) -> None:  # noqa: F811
    cid = _create(world, "template_ai", [world.ids["10000001"]], _ai_template(world))
    _run(world, FakeLlmClient([LlmError("LLM_UNAVAILABLE", retryable=False)]))
    draft = _draft(world, cid)
    assert draft.status == "failed"
    res = world.client.post(f"/api/v1/drafts/{draft.draft_id}/regenerate", headers=world.sales1)
    assert res.status_code == 202, res.text
    _run(world, FakeLlmClient([_para()]))
    again = _draft(world, cid)
    assert (again.status, again.last_error) == ("pending_review", None)
    assert again.gen_model == "fake-model"


def test_m4_06j_no_llm_injected_fails_without_network(world: World) -> None:  # noqa: F811
    """沒有注入假的 LLM 時，測試環境會直接失敗，不會連本機 Ollama（CLAUDE.md 第 6 節第 4 點）。"""
    cid = _create(world, "full_ai", [world.ids["10000001"]])
    deps = WorkerDeps(settings=world.settings, mailer=world.mailer, now=lambda: world.clock[0])
    run_until_idle(sessionmaker(bind=get_engine(), expire_on_commit=False), deps)
    world.db.expire_all()
    d = _draft(world, cid)
    assert (d.status, d.last_error) == ("failed", "LLM_DISABLED_IN_TEST")


def test_m4_06j_ai_drafts_never_skip_review(world: World) -> None:  # noqa: F811
    """CLAUDE.md 第 6 節：AI 草稿和模板草稿一樣，產生後是待審核，核准前不能寄。"""
    cid = _create(world, "full_ai", [world.ids["10000001"]])
    _run(world, FakeLlmClient([_mail()]))
    d = _draft(world, cid)
    assert d.status == "pending_review"
    with pytest.raises(Exception):  # noqa: B017, PT011
        draft_rules.ensure_sendable(d.status)
