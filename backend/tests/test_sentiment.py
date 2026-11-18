"""回覆態度（M4-07、F-TRK-2）。LLM 一律用 FakeLlmClient，不連本機 Ollama。"""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db import get_engine
from app.domain import ai_rules
from app.domain.company_rules import DomainError
from app.models import ActivityLog, CaseUpdate, Job
from app.services import ai_writer, sentiment_service
from app.services.llm import FakeLlmClient, LlmError
from app.workers.runner import WorkerDeps, run_until_idle
from tests.test_campaigns import World, world  # noqa: F401  （world 是 fixture）
from tests.test_cases import _cases, _send, _update


def _run(world: World, llm: FakeLlmClient) -> None:  # noqa: F811
    deps = WorkerDeps(settings=world.settings, mailer=world.mailer, now=lambda: world.clock[0], llm=llm)
    run_until_idle(sessionmaker(bind=get_engine(), expire_on_commit=False), deps)
    world.db.expire_all()


def _case_id(world: World) -> int:  # noqa: F811
    _send(world)
    return int(_cases(world)["items"][0]["case_id"])


def _manual_update(world: World, case_id: int) -> CaseUpdate:  # noqa: F811
    return world.db.scalars(
        select(CaseUpdate).where(CaseUpdate.case_id == case_id, CaseUpdate.channel != "system")
    ).one()


# ---------- domain（M4-07b）----------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"sentiment": "positive"}', "positive"),
        ('{"sentiment": " Negative "}', "negative"),
        ('好的：{"sentiment": "neutral"}', "neutral"),
        ('{"sentiment": "正面"}', "positive"),
        ('{"sentiment": "負面"}', "negative"),
        ('<think>想一下</think>{"sentiment": "中性"}', "neutral"),
    ],
)
def test_m4_07b_parse_sentiment_accepts_valid_values(raw: str, expected: str) -> None:
    assert ai_rules.parse_sentiment(raw) == expected


@pytest.mark.parametrize("raw", ['{"sentiment": "很開心"}', '{"other": "positive"}', '{"sentiment": 1}', "不是 JSON"])
def test_m4_07b_parse_sentiment_rejects_invalid(raw: str) -> None:
    with pytest.raises(DomainError) as e:
        ai_rules.parse_sentiment(raw)
    assert e.value.code in ("AI_BAD_SENTIMENT", "AI_BAD_JSON")


def test_m4_07c_check_sentiment_only_three_values() -> None:
    assert ai_rules.check_sentiment("positive") == "positive"
    with pytest.raises(DomainError) as e:
        ai_rules.check_sentiment("happy")
    assert e.value.code == "INVALID_SENTIMENT"


def test_m4_07b_prompt_is_versioned_file() -> None:
    system = ai_writer.load_system_prompt(sentiment_service.PROMPT_VERSION, "sentiment")
    assert "positive" in system and "neutral" in system and "negative" in system


# ---------- 排進佇列（M4-07b）----------
def test_m4_07b_update_with_note_enqueues_classification(world: World) -> None:  # noqa: F811
    case_id = _case_id(world)
    assert _update(world, case_id, note="客戶說想先看報價").status_code == 201
    jobs = world.db.scalars(select(Job).where(Job.kind == "classify_reply")).all()
    assert len(jobs) == 1 and jobs[0].payload["update_id"] == _manual_update(world, case_id).update_id


def test_m4_07b_update_without_note_does_not_enqueue(world: World) -> None:  # noqa: F811
    case_id = _case_id(world)
    assert _update(world, case_id).status_code == 201
    assert world.db.scalars(select(Job).where(Job.kind == "classify_reply")).all() == []


def test_m4_07b_worker_classifies_with_fake_llm(world: World) -> None:  # noqa: F811
    case_id = _case_id(world)
    _update(world, case_id, note="客戶說想先看報價")
    llm = FakeLlmClient(['{"sentiment": "positive"}'])
    _run(world, llm)
    u = _manual_update(world, case_id)
    assert (u.sentiment, u.sentiment_source) == ("positive", "ai")
    assert "想先看報價" in llm.requests[0].user  # 備註送給（本機）LLM 判斷
    detail = world.client.get(f"/api/v1/cases/{case_id}", headers=world.sales1).json()
    assert {(t["sentiment"], t["sentiment_source"]) for t in detail["timeline"]} == {(None, None), ("positive", "ai")}


def test_m4_07b_llm_failure_does_not_affect_the_update(world: World) -> None:  # noqa: F811
    case_id = _case_id(world)
    res = _update(world, case_id, note="客戶回信說再考慮")
    assert res.status_code == 201
    _run(world, FakeLlmClient([LlmError("LLM_UNAVAILABLE", retryable=False)]))
    u = _manual_update(world, case_id)
    assert (u.sentiment, u.sentiment_source) == (None, None)  # 留空，回填本身照常
    assert u.note == "客戶回信說再考慮"
    assert world.db.scalars(select(Job).where(Job.kind == "classify_reply")).one().status == "failed"
    assert _cases(world)["items"][0]["status"] == "replied"


def test_m4_07b_bad_output_is_retried_once_then_gives_up(world: World) -> None:  # noqa: F811
    case_id = _case_id(world)
    _update(world, case_id, note="不太確定")
    _run(world, FakeLlmClient(["亂回", '{"sentiment": "neutral"}']))  # 第一次不合格 → 重試 → 成功
    # 佇列退避 30 秒後才重試：時間往後撥再跑
    world.clock[0] = world.clock[0].replace(year=world.clock[0].year + 1)
    _run(world, FakeLlmClient(['{"sentiment": "neutral"}']))
    assert _manual_update(world, case_id).sentiment == "neutral"


# ---------- 手動修正（M4-07c）----------
def test_m4_07c_manual_correction_wins_and_is_logged(world: World) -> None:  # noqa: F811
    case_id = _case_id(world)
    _update(world, case_id, note="客戶說想先看報價")
    update_id = _manual_update(world, case_id).update_id
    # 業務在 AI 判斷完成前就先改了
    res = world.client.patch(
        f"/api/v1/cases/{case_id}/updates/{update_id}/sentiment", json={"sentiment": "negative"}, headers=world.sales1
    )
    assert res.status_code == 200, res.text
    _run(world, FakeLlmClient(['{"sentiment": "positive"}']))  # AI 後到也不會蓋掉手動的值
    u = _manual_update(world, case_id)
    assert (u.sentiment, u.sentiment_source) == ("negative", "manual")
    [log] = world.db.scalars(select(ActivityLog).where(ActivityLog.action == "case_sentiment")).all()
    assert (log.from_value, log.to_value, log.note) == (None, "negative", f"update:{update_id}")
    assert "想先看報價" not in (log.note or "")  # 稽核紀錄不放備註內容


def test_m4_07c_manual_correction_validates_and_enforces_access(world: World) -> None:  # noqa: F811
    case_id = _case_id(world)
    _update(world, case_id, note="備註")
    update_id = _manual_update(world, case_id).update_id
    url = f"/api/v1/cases/{case_id}/updates/{update_id}/sentiment"
    bad = world.client.patch(url, json={"sentiment": "happy"}, headers=world.sales1)
    assert (bad.status_code, bad.json()["error"]["code"]) == (422, "INVALID_SENTIMENT")
    other = world.client.patch(url, json={"sentiment": "positive"}, headers=world.sales2)
    assert other.status_code == 404  # 別人的案件一律當作不存在
    missing = world.client.patch(
        f"/api/v1/cases/{case_id}/updates/999999/sentiment", json={"sentiment": "positive"}, headers=world.sales1
    )
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "UPDATE_NOT_FOUND")
    ok = world.client.patch(url, json={"sentiment": "neutral"}, headers=world.manager)
    assert ok.status_code == 200  # 主管可以修正


# ---------- migration 0014（M4-07a）----------
def test_m4_07a_sentiment_columns_are_checked(world: World) -> None:  # noqa: F811
    case_id = _case_id(world)
    _update(world, case_id, note="備註")
    update_id = _manual_update(world, case_id).update_id
    db = world.db
    for sql in (
        "UPDATE case_update SET sentiment = 'happy', sentiment_source = 'ai' WHERE update_id = :u",
        "UPDATE case_update SET sentiment = 'positive', sentiment_source = 'robot' WHERE update_id = :u",
        "UPDATE case_update SET sentiment = 'positive' WHERE update_id = :u",  # 有態度一定要有來源
    ):
        with pytest.raises(IntegrityError):
            db.execute(text(sql), {"u": update_id})
        db.rollback()
    db.execute(
        text("UPDATE case_update SET sentiment = 'neutral', sentiment_source = 'manual' WHERE update_id = :u"),
        {"u": update_id},
    )
    db.rollback()
