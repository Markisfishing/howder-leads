# 0001 開發與測試用內嵌 PostgreSQL（pgserver），不依賴 Docker

- 日期：2026-11-17
- 狀態：採用

## 背景
CLAUDE.md 規定資料庫是 PostgreSQL 16，原本打算用 `docker-compose.yml` 起資料庫。開發這台電腦的 Docker Desktop 無法啟動（Inference manager 錯誤），而測試需要真的 Postgres（view、enum、TIMESTAMPTZ 行為和 SQLite 不同）。

## 決定
- 開發與測試改用 `pgserver` 套件內附的 PostgreSQL 16 執行檔（只在 dev 依賴）。
- `backend/scripts/pg_local.py` 負責啟動；專案路徑有中文時，先把執行檔複製到 `%LOCALAPPDATA%\howder\pginstall`（initdb 不支援非 ASCII 路徑）。
- 測試（`tests/conftest.py`）每次開一個獨立資料庫、跑完整 migration；開發資料庫用 `uv run python -m scripts.dev_db`。
- `docker-compose.yml` 保留，正式部署與能跑 Docker 的電腦照常使用。

## 理由
- 不需要安裝或修 Docker 就能跑測試，新同事 `uv sync` 後就能開發。
- 測試用的是真的 PostgreSQL，和正式環境行為一致。
- 只影響開發工具，正式環境不受影響。
