"""0013 績效與名單品質 view：v_case_perf、v_reject_reasons 加 share（M4-01a、M4-02a、F-TRK-5、F-MLE-1）

- v_case_perf：每件案件一列，在 v_case_fact（寄出、回覆、成交的定義只在那裡）之上，
  再帶負責業務、星等、標籤、寄出時用的模板與版本，給績效頁依星級／來源／標籤／模板／業務加總。
- v_reject_reasons：加上 share（該原因占同一批次排除總數的比例），前端只顯示，不重算。

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-18
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE VIEW v_case_perf AS
SELECT f.case_id, f.owner_id, u.display_name AS owner_name,
       f.is_sent, f.is_replied, f.is_won, f.won_amount, f.sent_at,
       f.priority, r.stars, f.fit_stars, f.source, r.tags,
       t.family_id AS template_family_id, t.name AS template_name, t.version AS template_version
FROM v_case_fact f
JOIN app_user u ON u.user_id = f.owner_id
JOIN v_recommendation r ON r.company_id = f.company_id
LEFT JOIN sales_case sc ON sc.case_id = f.case_id
LEFT JOIN email_message m ON m.message_id = sc.message_id
LEFT JOIN email_draft d ON d.draft_id = m.draft_id
LEFT JOIN campaign c ON c.campaign_id = d.campaign_id
LEFT JOIN email_template t ON t.template_id = c.template_id;

CREATE OR REPLACE VIEW v_reject_reasons AS
SELECT r.reject_reason, cl.run_id, count(*) AS n,
       round(count(*)::numeric / sum(count(*)) OVER (PARTITION BY cl.run_id), 4) AS share
FROM review r
JOIN classification cl ON cl.company_id = r.company_id AND cl.is_current
WHERE r.decision = 'rejected'
GROUP BY r.reject_reason, cl.run_id;
""")


def downgrade() -> None:
    op.execute("""
DROP VIEW v_case_perf;
DROP VIEW v_reject_reasons;
CREATE VIEW v_reject_reasons AS
SELECT r.reject_reason, cl.run_id, count(*) AS n
FROM review r
JOIN classification cl ON cl.company_id = r.company_id AND cl.is_current
WHERE r.decision = 'rejected'
GROUP BY r.reject_reason, cl.run_id;
""")
