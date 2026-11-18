"""0017 KPI 樣本門檻只定義一次：函式 kpi_min_sample()，v_kpi_summary 改用它（CLAUDE.md 第 4 節）

寄出少於這個件數就不算比例、標「樣本不足」。原本 10 同時寫在 v_kpi_summary 與 Python（metrics_service.MIN_SAMPLE）；
改成只在這個函式定義，view 直接呼叫，後端 metrics_service 啟動後讀一次。要調整門檻就新增 migration 改函式。
v_kpi_summary 的欄位與結果不變。

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-18
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

_VIEW = """
CREATE OR REPLACE VIEW v_kpi_summary AS
SELECT k.pending_review, k.total_companies, k.five_star, k.sent_7d, k.sent_total, k.replied_total,
       CASE WHEN k.sent_total >= {threshold} THEN round(k.replied_total::numeric / k.sent_total, 4) END AS reply_rate,
       k.won_total, k.won_amount_twd
FROM (
  SELECT
    (SELECT count(*) FROM company WHERE status = 'pending_review')                 AS pending_review,
    (SELECT count(*) FROM company)                                                 AS total_companies,
    (SELECT count(*) FROM v_recommendation WHERE stars = 5)                        AS five_star,
    (SELECT count(*) FROM email_message WHERE sent_at >= now() - interval '7 days') AS sent_7d,
    (SELECT count(*) FROM v_case_fact WHERE is_sent)                               AS sent_total,
    (SELECT count(*) FROM v_case_fact WHERE is_sent AND is_replied)                AS replied_total,
    (SELECT count(*) FROM v_case_fact WHERE is_won)                                AS won_total,
    (SELECT COALESCE(sum(won_amount), 0) FROM v_case_fact)                         AS won_amount_twd
) k;
"""


def upgrade() -> None:
    op.execute("CREATE FUNCTION kpi_min_sample() RETURNS integer LANGUAGE sql IMMUTABLE AS 'SELECT 10';")
    op.execute(_VIEW.format(threshold="kpi_min_sample()"))


def downgrade() -> None:
    op.execute(_VIEW.format(threshold="10"))
    op.execute("DROP FUNCTION kpi_min_sample();")
