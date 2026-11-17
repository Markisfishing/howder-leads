# 0002 Migration 用手寫 SQL，不用 Alembic autogenerate

- 日期：2026-11-17
- 狀態：採用

## 背景
資料庫有 view（`v_recommendation`、`v_kpi_summary`…）、enum、CHECK 約束與種子資料。KPI 規定只在 view 定義一次（CLAUDE.md 第 4 節第 4 點）。Alembic autogenerate 不會產生 view，對 enum 和 CHECK 的比對也不可靠。

## 決定
- 每個 migration 都是手寫 SQL（`migrations/sql/` 或 `op.execute`），ORM（`app/models`）只負責對應已經存在的表和 view，不拿來建表。
- `backend/db/schema.sql` 是給人看的完整 DDL，測試 `test_models` 會比對它和跑完 migration 的結果是否一致。

## 理由
- view 和 KPI 公式寫在 SQL 裡最清楚，也只有一份。
- 有測試防止 `schema.sql`、migration、ORM 三者不一致。
