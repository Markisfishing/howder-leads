"""測試共用 fixture。

資料庫：用 pgserver 啟動內嵌 PostgreSQL 16，每次測試 session 重建一個 howder_test 資料庫並跑完所有 migration；
每個測試結束後清空資料表（維度表保留）。
測試絕對不呼叫真實的 Claude 或 Microsoft Graph（CLAUDE.md 第 6 節）。
"""

import os
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from scripts import pg_local

BACKEND_DIR = Path(__file__).resolve().parent.parent
PG_DIR = Path(os.environ.get("HOWDER_TEST_PGDATA", Path(tempfile.gettempdir()) / "howder-test-pgdata"))

# 這些表每個測試後都清空；dim_* 是 migration 種子資料，保留
_DATA_TABLES = [
    "job",
    "user_mail_credential",
    "activity_log",
    "case_update",
    "sales_case",
    "email_event",
    "email_message",
    "email_draft",
    "campaign",
    "email_template",
    "contact",
    "gold_label",
    "review",
    "classification",
    "company",
    "import_batch",
    "model_run",
    "app_user",
]


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    _server, url = pg_local.start(PG_DIR, "howder_test", recreate=True)

    os.environ.update(
        DATABASE_URL=url,
        ENV="test",
        AUTH_MODE="dev",
        MAIL_MODE="sandbox",
        BOOTSTRAP_ADMIN_EMAILS="admin@example.com",
    )
    from app.config import get_settings
    from app.db import get_engine

    get_settings.cache_clear()
    get_engine.cache_clear()

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["database_url"] = url
    command.upgrade(cfg, "head")
    yield url
    get_engine().dispose()


@pytest.fixture
def db(database_url: str) -> Iterator[Session]:
    from app.db import get_engine

    session = sessionmaker(bind=get_engine(), expire_on_commit=False)()
    try:
        yield session
    finally:
        session.rollback()
        session.execute(text(f"TRUNCATE {', '.join(_DATA_TABLES)} RESTART IDENTITY CASCADE"))
        session.commit()
        session.close()


@pytest.fixture
def client(db: Session) -> TestClient:
    from app.main import create_app

    return TestClient(create_app())


@pytest.fixture
def as_user(client: TestClient) -> Callable[[str], dict[str, str]]:
    """回傳 dev 模式登入用的 header。email 開頭決定角色：admin@ → admin，manager@ → manager，其餘 sales。"""

    def _headers(email: str) -> dict[str, str]:
        headers = {"X-Dev-User": email}
        if email.startswith("manager@"):
            # 經理角色由 admin 指派；測試裡直接用 admin 把他升級
            uid = client.get("/api/v1/me", headers=headers).json()["user_id"]
            admin = {"X-Dev-User": "admin@example.com"}
            client.patch(f"/api/v1/admin/users/{uid}", json={"role": "manager"}, headers=admin)
        return headers

    return _headers


# 寄信流程的測試情境（test_campaigns.World）也給案件測試用
from tests.test_campaigns import world  # noqa: E402, F401
