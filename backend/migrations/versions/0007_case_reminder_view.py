"""0007 待辦提醒 view v_case_reminder（M3-10a、F-CASE-3、F-DASH-4）

提醒條件只在這裡定義一次（CLAUDE.md 第 4 節第 4 點），API、總覽頁都讀這個 view。
一件案件可以同時有多種提醒，每種一列。只看未結案的案件。

- overdue_report：最後一次寄信 7 天後還停在「已寄出」（沒有任何回填）
- follow_up_due：下次追蹤日已到（台灣日期）
- no_response：寄出 14 天沒回覆，worker 已標成「無回應」，建議電話或拜訪（直到回填或結案）

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-18
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

VIEW = """
CREATE VIEW v_case_reminder AS
WITH c AS (
  SELECT sc.case_id, sc.owner_id, sc.company_id, sc.status, sc.next_follow_up,
         coalesce((SELECT max(u.created_at) FROM case_update u
                   WHERE u.case_id = sc.case_id AND u.result = 'sent'), sc.opened_at) AS last_sent_at
  FROM sales_case sc
  WHERE sc.closed_at IS NULL
)
SELECT case_id, owner_id, company_id, 'overdue_report'::text AS kind, last_sent_at AS since
FROM c WHERE status = 'sent' AND last_sent_at <= now() - interval '7 days'
UNION ALL
SELECT case_id, owner_id, company_id, 'follow_up_due', next_follow_up::timestamptz
FROM c WHERE next_follow_up IS NOT NULL AND next_follow_up <= ((now() AT TIME ZONE 'UTC') + interval '8 hours')::date  -- 台灣日期（無日光節約）
UNION ALL
SELECT case_id, owner_id, company_id, 'no_response', last_sent_at
FROM c WHERE status = 'no_response';
"""


def upgrade() -> None:
    op.execute(VIEW)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_case_reminder;")
