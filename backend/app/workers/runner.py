"""背景 worker（ADR 0003）：從 PostgreSQL 佇列領工作來做。

啟動：uv run python -m app.workers
- 新增工作時資料庫會 NOTIFY job_queued，worker 收到就醒來；沒收到也每 WORKER_POLL_SECONDS 秒看一次
  （排程寄信的工作是 run_after 到了才做，靠輪詢接上）。
- 一次只做一筆，每筆都自己 commit；當掉留下的 running 工作 10 分鐘後收回重做。
"""

import logging
import os
import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import get_engine
from app.models import Job
from app.services import generator, jobs, reminder_service, send_service, sentiment_service
from app.services.llm import LlmClient, get_llm_client
from app.services.mailer import GraphMailer, Mailer, SandboxMailer

log = logging.getLogger("howder.worker")


@dataclass
class WorkerDeps:
    settings: Settings
    mailer: Mailer
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    llm: LlmClient | None = None  # 測試放 FakeLlmClient；沒放就依設定建立（ADR 0006）


def build_mailer(settings: Settings, session_factory: Callable[[], Session]) -> Mailer:
    """sandbox 一律不寄；live 才用 Graph，而且只用寄件人本人的權杖（ADR 0005）。"""
    if settings.mail_mode != "live":
        return SandboxMailer()
    from app.services import mail_token

    cipher = mail_token.TokenCipher(settings.mail_token_key)
    obo = mail_token.MsalOboClient(settings)

    def token_for(user_id: int) -> str:
        with session_factory() as s:  # 另開 session：不影響正在寄信的那個交易
            return mail_token.access_token_for(s, user_id, obo, cipher)

    return GraphMailer(token_for)


def _handle(db: Session, job: Job, deps: WorkerDeps) -> None:
    if job.kind == "generate_drafts":
        generator.run_generate_job(
            db,
            job.payload,
            llm_factory=lambda: deps.llm or get_llm_client(deps.settings),
            concurrency=deps.settings.llm_concurrency,
        )
    elif job.kind == "send_email":
        send_service.send_one(db, int(job.payload["draft_id"]), deps.mailer, deps.settings, deps.now())
    elif job.kind == sentiment_service.KIND:
        sentiment_service.classify_update(db, int(job.payload["update_id"]), deps.llm or get_llm_client(deps.settings))
    elif job.kind == reminder_service.DAILY_KIND:
        reminder_service.run_daily(db, deps.now())
    else:
        raise jobs.JobError("UNKNOWN_JOB_KIND", retryable=False)


def run_once(session_factory: Callable[[], Session], deps: WorkerDeps, worker_id: str = "worker") -> bool:
    """領一筆到期的工作來做。有做到工作回傳 True。測試直接呼叫這個。"""
    with session_factory() as db:
        job = jobs.claim_next(db, worker_id, deps.now())
        if job is None:
            return False
        job_id, kind = job.job_id, job.kind
        try:
            _handle(db, job, deps)
        except jobs.Reschedule as r:
            db.rollback()
            jobs.reschedule(db, db.get(Job, job_id) or job, r.run_after)
            return True
        except jobs.JobError as e:
            db.rollback()
            j = db.get(Job, job_id) or job
            retried = jobs.fail(db, j, e.code, deps.now(), retryable=e.retryable)
            log.warning("工作失敗 job=%s kind=%s code=%s 重試=%s", job_id, kind, e.code, retried)
            if not retried and kind == "send_email":
                send_service.mark_send_failed(db, int(j.payload["draft_id"]), e.code)
            return True
        except Exception as e:  # 不認得的錯誤也不能讓 worker 停掉
            db.rollback()
            j = db.get(Job, job_id) or job
            code = type(e).__name__
            retried = jobs.fail(db, j, code, deps.now())
            log.exception("工作發生未預期錯誤 job=%s kind=%s", job_id, kind)
            if not retried and kind == "send_email":
                send_service.mark_send_failed(db, int(j.payload["draft_id"]), code)
            return True
        jobs.complete(db, db.get(Job, job_id) or job, deps.now())
        return True


def run_until_idle(session_factory: Callable[[], Session], deps: WorkerDeps, limit: int = 1000) -> int:
    """把目前到期的工作全部做完（測試、手動補跑用）。回傳做了幾筆。"""
    n = 0
    while n < limit and run_once(session_factory, deps):
        n += 1
    return n


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    deps = WorkerDeps(settings=settings, mailer=build_mailer(settings, session_factory))
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    log.info("worker 啟動 id=%s mail_mode=%s", worker_id, settings.mail_mode)
    with session_factory() as db:
        reminder_service.ensure_daily_job(db, deps.now())  # 每日催辦（M3-10b）
    with psycopg.connect(url, autocommit=True) as listener:
        listener.execute("LISTEN job_queued")
        while True:
            with session_factory() as db:
                jobs.recover_stale(db, deps.now())
            run_until_idle(session_factory, deps)
            # 等 NOTIFY 或輪詢逾時
            for _ in listener.notifies(timeout=settings.worker_poll_seconds, stop_after=1):
                pass
