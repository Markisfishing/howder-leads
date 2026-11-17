"""ORM 欄位要和 migration 建出來的資料表一致（migration 是手寫 SQL，不靠 autogenerate）。"""

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models import Base


def _db_columns(db: Session, table: str) -> set[str]:
    rows = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"), {"t": table})
    return {r[0] for r in rows}


def test_orm_columns_exist_in_database(db: Session) -> None:
    for table in Base.metadata.tables.values():
        db_cols = _db_columns(db, table.name)
        assert db_cols, f"資料庫裡沒有 {table.name}"
        missing = {c.name for c in table.columns} - db_cols
        assert not missing, f"{table.name} 在資料庫缺少欄位：{missing}"


def _all_columns(url: str) -> set[tuple[str, str]]:
    engine = create_engine(url)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
            )
        )
        cols = {(r[0], r[1]) for r in rows}
    engine.dispose()
    return cols


def test_reference_schema_sql_matches_migrations(database_url: str) -> None:
    """db/schema.sql 是給人看的參考檔，要和 migration 跑完的結果一致（CLAUDE.md 第 5 節第 2 點）。"""
    check_url = database_url.rsplit("/", 1)[0] + "/howder_schema_check"
    admin = create_engine(database_url.rsplit("/", 1)[0] + "/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS howder_schema_check WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE howder_schema_check"))
    sql = (Path(__file__).resolve().parent.parent / "db" / "schema.sql").read_text(encoding="utf-8")
    engine = create_engine(check_url)
    with engine.begin() as conn:
        conn.exec_driver_sql(sql)
    engine.dispose()
    try:
        assert _all_columns(check_url) == _all_columns(database_url)
    finally:
        with admin.connect() as conn:
            conn.execute(text("DROP DATABASE IF EXISTS howder_schema_check WITH (FORCE)"))
        admin.dispose()


def test_seed_dimensions(db: Session) -> None:
    assert db.execute(text("SELECT count(*) FROM dim_industry")).scalar_one() == 19
    stars = dict(db.execute(text("SELECT priority, stars FROM dim_priority")).all())
    assert stars == {"A": 5, "B": 4, "C": 2, "D": 1}
