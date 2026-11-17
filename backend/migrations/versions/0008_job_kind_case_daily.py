"""0008 job.kind 加上 case_daily（M3-10b、F-CASE-3）

worker 每天台灣時間 6 點跑一次「每日催辦」：寄出 14 天沒回覆的案件標成無回應，做完排下一次。

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-18
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE job DROP CONSTRAINT job_kind_check;
ALTER TABLE job ADD CONSTRAINT job_kind_check CHECK (kind IN ('generate_drafts', 'send_email', 'case_daily'));
""")


def downgrade() -> None:
    op.execute("""
DELETE FROM job WHERE kind = 'case_daily';
ALTER TABLE job DROP CONSTRAINT job_kind_check;
ALTER TABLE job ADD CONSTRAINT job_kind_check CHECK (kind IN ('generate_drafts', 'send_email'));
""")
