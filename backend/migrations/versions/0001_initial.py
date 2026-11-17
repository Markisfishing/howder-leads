"""0001 初始 schema 與維度表種子資料

SQL 內容在 migrations/sql/0001_initial.sql（從 db/schema.sql 凍結複製）。

Revision ID: 0001
Revises:
Create Date: 2026-11-17
"""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SQL_FILE = Path(__file__).resolve().parent.parent / "sql" / "0001_initial.sql"

_VIEWS = ["v_kpi_summary", "v_reject_reasons", "v_win_rate_by_priority", "v_funnel", "v_recommendation"]
_TABLES = [
    "activity_log", "opportunity", "email_event", "email_message", "email_draft", "campaign",
    "email_template", "contact", "gold_label", "review", "classification", "company",
    "import_batch", "model_run", "dim_priority", "dim_industry", "app_user",
]
_TYPES = ["draft_status", "gen_mode", "company_status", "user_role"]


def upgrade() -> None:
    op.execute(SQL_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    for v in _VIEWS:
        op.execute(f"DROP VIEW IF EXISTS {v}")
    for t in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    for t in _TYPES:
        op.execute(f"DROP TYPE IF EXISTS {t}")
