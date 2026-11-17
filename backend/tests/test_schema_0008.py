"""migration 0008：job.kind 接受 case_daily，其他值仍然擋下。"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Job


def test_m3_10b_job_kind_case_daily_allowed(db: Session) -> None:
    db.add(Job(kind="case_daily", payload={}))
    db.flush()
    db.add(Job(kind="unknown", payload={}))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
