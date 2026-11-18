"""migration 0012：email_draft 有 gen_provider、gen_model、prompt_version，舊資料為空。"""

from sqlalchemy import text
from sqlalchemy.orm import Session


def test_m4_06h_draft_generation_columns_exist_and_nullable(db: Session) -> None:
    rows = db.execute(
        text(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_name = 'email_draft' AND column_name IN ('gen_provider', 'gen_model', 'prompt_version')"
        )
    ).all()
    assert {r[0]: r[1] for r in rows} == {"gen_provider": "YES", "gen_model": "YES", "prompt_version": "YES"}
