"""0002 v_kpi_summary 加上回覆率 reply_rate

比例也在 view 算好（CLAUDE.md 第 4 節第 4 點），寄出未滿 10 封時回傳 NULL，前端顯示「—」。

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_BASE = """
SELECT
  (SELECT count(*) FROM company WHERE status = 'pending_review')                 AS pending_review,
  (SELECT count(*) FROM company)                                                 AS total_companies,
  (SELECT count(*) FROM v_recommendation WHERE stars = 5)                        AS five_star,
  (SELECT count(*) FROM email_message WHERE sent_at >= now() - interval '7 days') AS sent_7d,
  (SELECT count(*) FROM email_message)                                           AS sent_total,
  (SELECT count(DISTINCT message_id) FROM email_event WHERE event_type = 'replied') AS replied_total
"""


def upgrade() -> None:
    op.execute(f"""
CREATE OR REPLACE VIEW v_kpi_summary AS
SELECT k.*,
       CASE WHEN k.sent_total >= 10 THEN round(k.replied_total::numeric / k.sent_total, 4) END AS reply_rate
FROM ({_BASE}) k
""")


def downgrade() -> None:
    op.execute("DROP VIEW v_kpi_summary")
    op.execute(f"CREATE VIEW v_kpi_summary AS {_BASE}")
