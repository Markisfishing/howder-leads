"""PostgreSQL 背景工作佇列（ADR 0003）。

worker 用 SELECT … FOR UPDATE SKIP LOCKED 領工作，所以多個 worker 同時跑也不會領到同一筆。
新增工作時資料庫會 NOTIFY job_queued（migration 0003 的觸發器）。
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Job

BACKOFF_BASE_SECONDS = 30  # 第 1 次失敗 30 秒後重試、第 2 次 60 秒…（指數退避）
STALE_AFTER = timedelta(minutes=10)  # worker 當掉時，running 超過這麼久就收回重做


class JobError(Exception):
    """handler 失敗。retryable=False 時不再重試（例如資料本身有問題）。code 會寫進 last_error，不放信件內容。"""

    def __init__(self, code: str, retryable: bool = True) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class Reschedule(Exception):  # noqa: N818 - 這不是錯誤，是「晚點再做」的訊號
    """handler 要求晚點再做（例如今天已達寄送上限），不算一次失敗。"""

    def __init__(self, run_after: datetime) -> None:
        super().__init__(run_after.isoformat())
        self.run_after = run_after


def enqueue(
    db: Session,
    kind: str,
    payload: dict[str, Any],
    *,
    run_after: datetime | None = None,
    created_by: int | None = None,
    max_attempts: int = 3,
) -> Job:
    """新增工作（不 commit，和呼叫端的資料一起 commit，才不會有資料沒存但工作已排的情況）。"""
    job = Job(kind=kind, payload=payload, created_by=created_by, max_attempts=max_attempts)
    if run_after is not None:
        job.run_after = run_after
    db.add(job)
    db.flush()
    return job


def claim_next(db: Session, worker_id: str, now: datetime) -> Job | None:
    """領一筆到期的工作，標成 running 後 commit。沒有工作就回傳 None。"""
    job = db.scalar(
        select(Job)
        .where(Job.status == "queued", Job.run_after <= now)
        .order_by(Job.run_after, Job.job_id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        db.rollback()
        return None
    job.status = "running"
    job.attempts += 1
    job.locked_at = now
    job.locked_by = worker_id
    db.commit()
    return job


def complete(db: Session, job: Job, now: datetime) -> None:
    job.status = "done"
    job.finished_at = now
    job.last_error = None
    db.commit()


def fail(db: Session, job: Job, code: str, now: datetime, *, retryable: bool = True) -> bool:
    """記錄失敗。還能重試就排回佇列（指數退避）並回傳 True；不能重試就標成 failed 回傳 False。"""
    job.last_error = code[:200]
    job.locked_at = None
    job.locked_by = None
    if retryable and job.attempts < job.max_attempts:
        job.status = "queued"
        job.run_after = now + timedelta(seconds=BACKOFF_BASE_SECONDS * 2 ** (job.attempts - 1))
        db.commit()
        return True
    job.status = "failed"
    job.finished_at = now
    db.commit()
    return False


def reschedule(db: Session, job: Job, run_after: datetime) -> None:
    """晚點再做，不算一次嘗試。"""
    job.status = "queued"
    job.attempts = max(job.attempts - 1, 0)
    job.run_after = run_after
    job.locked_at = None
    job.locked_by = None
    db.commit()


def recover_stale(db: Session, now: datetime) -> int:
    """worker 當掉留下的 running 工作，超過 STALE_AFTER 就放回佇列。"""
    stale = list(
        db.scalars(
            select(Job)
            .where(Job.status == "running", Job.locked_at < now - STALE_AFTER)
            .with_for_update(skip_locked=True)
        )
    )
    for job in stale:
        job.status = "queued"
        job.locked_at = None
        job.locked_by = None
    db.commit()
    return len(stale)
