# 0003 背景工作佇列改用 PostgreSQL，不用 arq + Redis

- 日期：2026-11-17
- 狀態：採用（使用者於 2026-11-17 決定）
- 取代：CLAUDE.md 第 3 節、SPEC 第 5 節、第 7.1 節原本的「arq + Redis」

## 背景
M2 需要背景工作：產生草稿（F-MAIL-3）、排程寄信與限速（F-MAIL-6），M3 還要同步回覆。原本規劃用 arq，但 arq 必須有 Redis。開發這台電腦的 Docker 起不來（ADR 0001），Windows 上也沒有官方 Redis。

## 決定
- 佇列放在 PostgreSQL 的 `job` 資料表（M2-11 的 migration 0003 建立）。
- worker 用 `SELECT … FOR UPDATE SKIP LOCKED` 一次領一筆工作，多個 worker 也不會領到同一筆。
- 欄位：`kind`、`payload`、`status`（queued / running / done / failed）、`run_after`（排程與重試用）、`attempts`、`last_error`、`created_at`、`finished_at`。
- 新工作用 `LISTEN/NOTIFY` 叫醒 worker；沒收到通知時每幾秒輪詢一次當作保險。
- 失敗時依 `attempts` 做指數退避，把 `run_after` 往後延；第 3 次還失敗就標成 `failed`（SPEC 9 可用性）。
- API 照舊只回傳 `job_id`（CLAUDE.md 第 4 節第 6 點），前端用 `job_id` 查進度。
- worker 和 API 是同一個 Python 套件，入口放在 `app/workers/`，用 `uv run python -m app.workers` 啟動。
- 部署少一個 Redis 容器；`docker-compose.yml` 拿掉 redis。

## 理由
- 不用多裝、多維護一個服務。開發、測試、正式環境都只要 PostgreSQL，測試也能直接用 ADR 0001 的內嵌 Postgres。
- 「建立草稿」和「排入工作」可以放在同一個資料庫交易裡，不會發生資料寫進去了、工作卻沒排到（或反過來）的情況。
- 量很小：每位業務每天最多 50 封，PostgreSQL 綽綽有餘。
- 工作紀錄留在資料庫，查得到失敗原因，也方便寫進稽核紀錄。

## 代價
- 輪詢、重試、逾時回收都要自己寫（約一兩百行），而且要有測試。
- 如果之後量變得很大（每秒上百個工作），再評估換回專用的佇列。
