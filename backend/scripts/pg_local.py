"""不用 Docker 的本機 PostgreSQL 16（pgserver），給開發與測試用。

為什麼要複製執行檔：專案路徑含中文（D:\\project\\後達電子），pgserver 的 initdb/pg_ctl 放在 .venv 裡，
Postgres 在 Windows 上無法處理非 ASCII 的執行檔路徑。所以第一次使用時，把 pgserver 內附的
Postgres 複製到 %LOCALAPPDATA%\\howder\\pginstall-<代碼>（純英文路徑，每份 checkout 各一份），再把 pgserver 指向那裡。
資料目錄同理，也要放在純英文路徑。
"""

import hashlib
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
    # 每個來源（不同 checkout 的 .venv）各複製到自己的資料夾。共用同一個資料夾的話，
    # 另一份 checkout 的 Postgres 還開著時要整個重新複製，會因檔案被佔用而失敗。
    dst = HOWDER_HOME / f"pginstall-{hashlib.sha1(str(src).encode('utf-8')).hexdigest()[:8]}"
    marker = dst / ".copied-from"
    required_binaries = ("postgres.exe", "pg_ctl.exe", "initdb.exe", "psql.exe")
    bin_path = dst / "bin"
    has_required_binaries = all((bin_path / name).is_file() for name in required_binaries)
    if not marker.exists() or marker.read_text(encoding="utf-8") != str(src) or not has_required_binaries:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        marker.write_text(str(src), encoding="utf-8")
    pg_commands.POSTGRES_BIN_PATH = bin_path
    pg_server_mod.POSTGRES_BIN_PATH = bin_path  # type: ignore[attr-defined]


def start(data_dir: Path, dbname: str, recreate: bool = False, cleanup_mode: str = "stop") -> tuple[Any, str]:
    """啟動（或接上已啟動的）本機 Postgres，確保資料庫存在，回傳 (server, SQLAlchemy 連線網址)。

    cleanup_mode：程式結束時 "stop" 只停掉資料庫（開發用，資料保留）；"delete" 連資料目錄一起刪（測試用）。
    """
    if not str(data_dir).isascii():
        raise ValueError(f"資料目錄必須是純英文路徑：{data_dir}")
    _ensure_ascii_binaries()
    data_dir.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(data_dir, cleanup_mode=cleanup_mode)
    if recreate:
        server.psql(f"DROP DATABASE IF EXISTS {dbname} WITH (FORCE);")
    if "(0 rows)" in server.psql(f"SELECT 1 FROM pg_database WHERE datname = '{dbname}';"):
        server.psql(f"CREATE DATABASE {dbname};")
    return server, server.get_uri(dbname).replace("postgresql://", "postgresql+psycopg://")
