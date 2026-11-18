"""migration 0011：campaign.status 接受 ready（待寄出），其他值仍然擋下。"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _insert(db: Session, status: str) -> None:
    uid = db.execute(text("SELECT user_id FROM app_user ORDER BY user_id LIMIT 1")).scalar_one_or_none()
    if uid is None:
        uid = db.execute(
            text(
                "INSERT INTO app_user (email, display_name, role) "
                "VALUES ('u@example.com', 'u', 'sales') RETURNING user_id"
            )
        ).scalar_one()
    db.execute(
        text("INSERT INTO campaign (name, owner_id, status) VALUES ('測試批次', :u, :s)"), {"u": uid, "s": status}
    )
    db.flush()


def test_m2_16_campaign_status_ready_allowed(db: Session) -> None:
    _insert(db, "ready")
    with pytest.raises(IntegrityError):
        _insert(db, "unknown")
    db.rollback()
