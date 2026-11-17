"""M2-11 migration 0003：背景工作佇列（ADR 0003）、寄信權杖（ADR 0005）、寄送欄位。"""

import threading
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import AppUser, Job, UserMailCredential

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _psycopg_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def _user(db: Session, email: str = "sales1@example.com") -> AppUser:
    u = AppUser(email=email, display_name="sales1", role="sales")
    db.add(u)
    db.flush()
    return u


def test_m2_11_job_defaults(db: Session) -> None:
    job = Job(kind="send_email", payload={"draft_id": 1})
    db.add(job)
    db.flush()
    db.refresh(job)
    assert job.status == "queued"
    assert job.attempts == 0
    assert job.max_attempts == 3
    assert job.run_after is not None


@pytest.mark.parametrize(
    ("column", "value"),
    [("status", "'paused'"), ("attempts", "-1"), ("max_attempts", "0")],
)
def test_m2_11_job_check_constraints(db: Session, column: str, value: str) -> None:
    with pytest.raises(IntegrityError):
        db.execute(text(f"INSERT INTO job (kind, {column}) VALUES ('send_email', {value})"))
    db.rollback()


def test_m2_11_job_kind_check_rejects_unknown_kind(db: Session) -> None:
    with pytest.raises(IntegrityError):
        db.execute(text("INSERT INTO job (kind) VALUES ('bogus')"))
    db.rollback()


def test_m2_11_job_insert_notifies_worker(database_url: str) -> None:
    """新增 queued 工作時會 NOTIFY job_queued，worker 不用一直輪詢。"""
    url = _psycopg_url(database_url)
    with psycopg.connect(url, autocommit=True) as listener:
        listener.execute("LISTEN job_queued")

        def insert() -> None:
            with psycopg.connect(url, autocommit=True) as writer:
                writer.execute("INSERT INTO job (kind) VALUES ('generate_drafts')")

        t = threading.Thread(target=insert)
        t.start()
        t.join()
        received = [n.payload for n in listener.notifies(timeout=5, stop_after=1)]
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("TRUNCATE job RESTART IDENTITY")
    assert received == ["generate_drafts"]


def test_m2_11_skip_locked_gives_each_worker_a_different_job(database_url: str, db: Session) -> None:
    """兩個 worker 同時領工作，不會領到同一筆（ADR 0003）。"""
    db.add_all([Job(kind="send_email"), Job(kind="send_email")])
    db.commit()

    claim = text(
        "SELECT job_id FROM job WHERE status = 'queued' AND run_after <= now() "
        "ORDER BY run_after, job_id FOR UPDATE SKIP LOCKED LIMIT 1"
    )
    engine = create_engine(database_url)
    try:
        worker_a = sessionmaker(bind=engine)()
        worker_b = sessionmaker(bind=engine)()
        first = worker_a.execute(claim).scalar_one()
        second = worker_b.execute(claim).scalar_one()
        assert first != second
        worker_a.rollback()
        worker_b.rollback()
        worker_a.close()
        worker_b.close()
    finally:
        engine.dispose()


def test_m2_11_campaign_status_check(db: Session) -> None:
    u = _user(db)
    db.execute(
        text("INSERT INTO campaign (name, owner_id, status) VALUES ('ok', :u, 'reviewing')"),
        {"u": u.user_id},
    )
    with pytest.raises(IntegrityError):
        db.execute(
            text("INSERT INTO campaign (name, owner_id, status) VALUES ('bad', :u, 'whatever')"),
            {"u": u.user_id},
        )
    db.rollback()


def test_m2_11_email_draft_send_columns(db: Session) -> None:
    cols = {
        r[0]: r[1]
        for r in db.execute(
            text(
                "SELECT column_name, column_default FROM information_schema.columns "
                "WHERE table_name = 'email_draft' AND column_name IN ('scheduled_at','send_attempts','last_error')"
            )
        )
    }
    assert set(cols) == {"scheduled_at", "send_attempts", "last_error"}
    assert cols["send_attempts"] == "0"


def test_m2_11_mail_credential_status_check(db: Session) -> None:
    u = _user(db)
    db.add(UserMailCredential(user_id=u.user_id, token_cache=b"encrypted", scopes=["Mail.Send"]))
    db.flush()
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE user_mail_credential SET status = 'stolen' WHERE user_id = :u"), {"u": u.user_id})
    db.rollback()


def test_m2_11_mail_credential_repr_hides_token(db: Session) -> None:
    """ADR 0005：權杖不可以出現在 log；repr 不含 token_cache。"""
    cred = UserMailCredential(user_id=1, token_cache=b"super-secret-cache", scopes=["Mail.Send"], status="connected")
    assert "super-secret" not in repr(cred)
    assert "token_cache" not in repr(cred)


def test_m2_11_mail_credential_deleted_with_user(db: Session) -> None:
    u = _user(db)
    db.add(UserMailCredential(user_id=u.user_id, token_cache=b"x", scopes=["Mail.Send"]))
    db.flush()
    db.execute(text("DELETE FROM app_user WHERE user_id = :u"), {"u": u.user_id})
    assert db.execute(text("SELECT count(*) FROM user_mail_credential")).scalar_one() == 0


def test_m2_11_downgrade_and_upgrade_again(database_url: str) -> None:
    """migration 0003 可以退回 0002 再升回 head（在另一個資料庫上跑，不影響其他測試）。"""
    base = database_url.rsplit("/", 1)[0]
    check_url = base + "/howder_migration_check"
    admin = create_engine(base + "/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS howder_migration_check WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE howder_migration_check"))
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["database_url"] = check_url
    try:
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "0002")
        engine = create_engine(check_url)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT to_regclass('job')")).scalar_one() is None
        engine.dispose()
        command.upgrade(cfg, "head")
        engine = create_engine(check_url)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT to_regclass('job')")).scalar_one() == "job"
        engine.dispose()
    finally:
        with admin.connect() as conn:
            conn.execute(text("DROP DATABASE IF EXISTS howder_migration_check WITH (FORCE)"))
        admin.dispose()
