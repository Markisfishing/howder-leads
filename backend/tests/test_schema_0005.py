"""migration 0005：模板版本與純文字內文。"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import EmailTemplate


def _template(db: Session, family: int | None, version: int, active: bool) -> EmailTemplate:
    t = EmailTemplate(
        name="邀請信", subject="主旨", body_text="內文", body_html="<p>內文</p>", version=version, is_active=active
    )
    db.add(t)
    db.flush()
    t.family_id = family or t.template_id
    db.flush()
    return t


def test_m2_02a_only_one_active_version_per_family(db: Session) -> None:
    first = _template(db, None, 1, True)
    _template(db, first.family_id, 2, False)
    with pytest.raises(IntegrityError):
        _template(db, first.family_id, 3, True)
    db.rollback()


def test_m2_02a_version_number_unique_in_family(db: Session) -> None:
    first = _template(db, None, 1, True)
    with pytest.raises(IntegrityError):
        _template(db, first.family_id, 1, False)
    db.rollback()


def test_m2_05a_draft_has_body_text(db: Session) -> None:
    col = db.execute(
        text(
            "SELECT column_default, is_nullable FROM information_schema.columns "
            "WHERE table_name = 'email_draft' AND column_name = 'body_text'"
        )
    ).one()
    assert col.is_nullable == "NO"
