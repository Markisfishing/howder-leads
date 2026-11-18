"""migration 0015：company_site_summary 的 CHECK 與 job.kind 接受 fetch_site（M4-08a）。"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _company(db: Session) -> int:
    return int(
        db.execute(
            text(
                "INSERT INTO company (tax_id, name, status) "
                "VALUES ('93000001', '摘要測試公司', 'pending_review') RETURNING company_id"
            )
        ).scalar_one()
    )


def test_m4_08a_summary_status_and_consistency_checked(db: Session) -> None:
    cid = _company(db)
    ok = "INSERT INTO company_site_summary (company_id, summary, status) VALUES (:c, '做端子台', 'ok')"
    db.execute(text(ok), {"c": cid})
    db.flush()
    for sql in (
        "INSERT INTO company_site_summary (company_id, status, error_code) VALUES (:c, 'unknown', 'X')",
        "INSERT INTO company_site_summary (company_id, status) VALUES (:c, 'ok')",  # ok 一定要有摘要
        "INSERT INTO company_site_summary (company_id, summary, status, error_code) VALUES (:c, 'x', 'failed', 'E')",
        "INSERT INTO company_site_summary (company_id, status) VALUES (:c, 'failed')",  # failed 一定要有錯誤代碼
    ):
        with pytest.raises(IntegrityError):
            db.execute(text(sql), {"c": cid + 1000})
            db.flush()
        db.rollback()


def test_m4_08a_job_kind_accepts_fetch_site(db: Session) -> None:
    db.execute(text("INSERT INTO job (kind, payload) VALUES ('fetch_site', '{}')"))
    db.flush()
    with pytest.raises(IntegrityError):
        db.execute(text("INSERT INTO job (kind, payload) VALUES ('no_such_kind', '{}')"))
        db.flush()
    db.rollback()
