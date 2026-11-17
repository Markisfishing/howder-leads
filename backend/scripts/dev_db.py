"""不用 Docker 的開發資料庫：啟動內嵌的 PostgreSQL 16 並保持執行。

用法（在 backend/ 底下）：
    uv run python -m scripts.dev_db
啟動後會印出 DATABASE_URL，填進 backend/.env，再執行 `uv run alembic upgrade head`。按 Ctrl+C 結束。
資料存放在 %LOCALAPPDATA%\\howder\\pgdata，可以用環境變數 HOWDER_PGDATA 改（必須是純英文路徑）。
"""

import os
import time
from pathlib import Path

from scripts.pg_local import HOWDER_HOME, start


def main() -> None:
    data_dir = Path(os.environ.get("HOWDER_PGDATA", HOWDER_HOME / "pgdata"))
    _server, url = start(data_dir, "howder")
    print(f"DATABASE_URL={url}", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
