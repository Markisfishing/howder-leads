"""ORM 欄位要和 migration 建出來的資料表一致（migration 是手寫 SQL，不靠 autogenerate）。"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Base


def _db_columns(db: Session, table: str) -> set[str]:
    rows = db.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"), {"t": table}
    )
    return {r[0] for r in rows}


def test_orm_columns_exist_in_database(db: Session) -> None:
    for table in Base.metadata.tables.values():
        db_cols = _db_columns(db, table.name)
        assert db_cols, f"資料庫裡沒有 {table.name}"
        missing = {c.name for c in table.columns} - db_cols
        assert not missing, f"{table.name} 在資料庫缺少欄位：{missing}"


def test_seed_dimensions(db: Session) -> None:
    assert db.execute(text("SELECT count(*) FROM dim_industry")).scalar_one() == 19
    stars = dict(db.execute(text("SELECT priority, stars FROM dim_priority")).tuples().all())
    assert stars == {"A": 5, "B": 4, "C": 2, "D": 1}
