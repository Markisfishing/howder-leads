"""不用 Docker 的本機 PostgreSQL 16（pgserver），給開發與測試用。

為什麼要複製執行檔：專案路徑含中文（D:\\project\\後達電子），pgserver 的 initdb/pg_ctl 放在 .venv 裡，
Postgres 在 Windows 上無法處理非 ASCII 的執行檔路徑。所以第一次使用時，把 pgserver 內附的
Postgres 複製到 %LOCALAPPDATA%\\howder\\pginstall（純英文路徑），再把 pgserver 指向那裡。
資料目錄同理，也要放在純英文路徑。
"""

import os
import shutil
from pathlib import Path
from typing import Any

import pgserver
import pgserver._commands as pg_commands
import pgserver.postgres_server as pg_server_mod

HOWDER_HOME = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "howder"


def _ensure_ascii_binaries() -> None:
    src = Path(pgserver.__file__).parent / "pginstall"
    if str(src).isascii():
        return
    dst = HOWDER_HOME / "pginstall"
    marker = dst / ".copied-from"
    if not marker.exists() or marker.read_text(encoding="utf-8") != str(src):
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        marker.write_text(str(src), encoding="utf-8")
    bin_path = dst / "bin"
    pg_commands.POSTGRES_BIN_PATH = bin_path
    pg_server_mod.POSTGRES_BIN_PATH = bin_path  # type: ignore[attr-defined]


def start(data_dir: Path, dbname: str, recreate: bool = False) -> tuple[Any, str]:
    """啟動（或接上已啟動的）本機 Postgres，確保資料庫存在，回傳 (server, SQLAlchemy 連線網址)。"""
    if not str(data_dir).isascii():
        raise ValueError(f"資料目錄必須是純英文路徑：{data_dir}")
    _ensure_ascii_binaries()
    data_dir.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(data_dir, cleanup_mode="stop")
    if recreate:
        server.psql(f"DROP DATABASE IF EXISTS {dbname} WITH (FORCE);")
    if "(0 rows)" in server.psql(f"SELECT 1 FROM pg_database WHERE datname = '{dbname}';"):
        server.psql(f"CREATE DATABASE {dbname};")
    return server, server.get_uri(dbname).replace("postgresql://", "postgresql+psycopg://")
