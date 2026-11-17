"""不用 Docker 的開發資料庫：用 pgserver 啟動內嵌的 PostgreSQL 16。

用法：
    uv run python scripts/dev_db.py          # 啟動並印出 DATABASE_URL，按 Ctrl+C 結束
資料存放位置預設是 %LOCALAPPDATA%/howder/pgdata（路徑不能有中文，Postgres 在 Windows 會讀不到），
可以用環境變數 HOWDER_PGDATA 改。
"""

import os
import time
from pathlib import Path

import pgserver


def data_dir() -> Path:
    default = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "howder" / "pgdata"
    return Path(os.environ.get("HOWDER_PGDATA", default))


def main() -> None:
    path = data_dir()
    path.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(path, cleanup_mode="stop")
    exists = server.psql("SELECT 1 FROM pg_database WHERE datname = 'howder';")
    if "(0 rows)" in exists:
        server.psql("CREATE DATABASE howder;")
    uri = server.get_uri("howder").replace("postgresql://", "postgresql+psycopg://")
    print(f"DATABASE_URL={uri}", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
