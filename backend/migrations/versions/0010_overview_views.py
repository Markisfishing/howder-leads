"""0010 總覽頁 view：v_case_fact、v_company_fact；v_kpi_summary 的回覆率改用案件（M3-12a、F-DASH-1～3）

「寄出」「回覆」「成交」的定義只在這裡（CLAUDE.md 第 4 節第 4 點）：
- 寄出 is_sent：案件時間軸有一筆 result = 'sent'（寄信成功時系統自動寫入；「加入追蹤」沒寄信的案件不算）
- 回覆 is_replied：業務回填過 replied／negotiating／won 任一種（客戶有回應）
- 成交 is_won：案件狀態 won；金額 won_amount 只算成交的案件
回覆率 = 已寄出且有回覆的案件 ÷ 已寄出的案件；不再讀 email_event（ADR 0004：系統不讀業務信箱）。

- v_case_fact：每件案件一列，帶公司的產業、來源、產品類型、優先級，給總覽依條件篩選加總
- v_company_fact：每家公司一列，名單漏斗用（名單 → 審核通過 → 已寄信 → 回覆 → 成交）
- v_kpi_summary：sent_total／replied_total 改成案件數；最後面加上 won_total、won_amount_twd

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-18
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

CASE_FACT = """
CREATE VIEW v_case_fact AS
SELECT sc.case_id, sc.case_no, sc.company_id, sc.owner_id, sc.origin, sc.status,
       sc.opened_at, sc.closed_at,
       s.first_sent_at                                  AS sent_at,
       (s.first_sent_at IS NOT NULL)                    AS is_sent,
       EXISTS (SELECT 1 FROM case_update u
               WHERE u.case_id = sc.case_id
                 AND u.result IN ('replied','negotiating','won')) AS is_replied,
       (sc.status = 'won')                              AS is_won,
       CASE WHEN sc.status = 'won' THEN sc.amount_twd END AS won_amount,
       r.industry_id, r.industry, r.source, r.product_type, r.priority, r.fit_stars
FROM sales_case sc
LEFT JOIN LATERAL (SELECT min(u.created_at) AS first_sent_at
                   FROM case_update u
                   WHERE u.case_id = sc.case_id AND u.result = 'sent') s ON TRUE
JOIN v_recommendation r ON r.company_id = sc.company_id;
"""

COMPANY_FACT = """
CREATE VIEW v_company_fact AS
SELECT r.company_id, r.status, r.owner_id, r.industry_id, r.source, r.product_type,
       r.priority, r.stars, r.fit_stars, c.created_at,
       (r.status NOT IN ('imported','pending_review','rejected'))  AS is_approved,
       COALESCE(bool_or(f.is_sent), FALSE)                         AS is_sent,
       COALESCE(bool_or(f.is_sent AND f.is_replied), FALSE)        AS is_replied,
       COALESCE(bool_or(f.is_won), FALSE)                          AS is_won,
       min(f.sent_at)                                              AS first_sent_at
FROM v_recommendation r
JOIN company c ON c.company_id = r.company_id
LEFT JOIN v_case_fact f ON f.company_id = r.company_id
GROUP BY r.company_id, r.status, r.owner_id, r.industry_id, r.source, r.product_type,
         r.priority, r.stars, r.fit_stars, c.created_at;
"""

KPI_COLUMNS = """
    (SELECT count(*) FROM company WHERE status = 'pending_review')                 AS pending_review,
    (SELECT count(*) FROM company)                                                 AS total_companies,
    (SELECT count(*) FROM v_recommendation WHERE stars = 5)                        AS five_star,
    (SELECT count(*) FROM email_message WHERE sent_at >= now() - interval '7 days') AS sent_7d,"""

KPI_NEW = f"""
CREATE OR REPLACE VIEW v_kpi_summary AS
SELECT k.pending_review, k.total_companies, k.five_star, k.sent_7d, k.sent_total, k.replied_total,
       CASE WHEN k.sent_total >= 10 THEN round(k.replied_total::numeric / k.sent_total, 4) END AS reply_rate,
       k.won_total, k.won_amount_twd
FROM (
  SELECT{KPI_COLUMNS}
    (SELECT count(*) FROM v_case_fact WHERE is_sent)                               AS sent_total,
    (SELECT count(*) FROM v_case_fact WHERE is_sent AND is_replied)                AS replied_total,
    (SELECT count(*) FROM v_case_fact WHERE is_won)                                AS won_total,
    (SELECT COALESCE(sum(won_amount), 0) FROM v_case_fact)                         AS won_amount_twd
) k;
"""

KPI_OLD = f"""
CREATE VIEW v_kpi_summary AS
SELECT k.*,
       CASE WHEN k.sent_total >= 10 THEN round(k.replied_total::numeric / k.sent_total, 4) END AS reply_rate
FROM (
  SELECT{KPI_COLUMNS}
    (SELECT count(*) FROM email_message)                                           AS sent_total,
    (SELECT count(DISTINCT message_id) FROM email_event WHERE event_type = 'replied') AS replied_total
) k;
"""


def upgrade() -> None:
    op.execute(CASE_FACT + COMPANY_FACT + KPI_NEW)


def downgrade() -> None:
    op.execute("DROP VIEW v_kpi_summary;" + KPI_OLD + "DROP VIEW v_company_fact; DROP VIEW v_case_fact;")
