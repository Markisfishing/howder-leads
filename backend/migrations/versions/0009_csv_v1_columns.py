"""0009 CSV 欄位規格 v1（M3-06a、SPEC 8.4、F-REC-7）

- company：country（ISO 兩碼，預設 TW）、url_status（valid／invalid／unchecked）、source（資料來源網站代號）
- classification：fit_stars（1.0～5.0，小數一位；沒給就用優先級對照的星等）、product_type、tags
- import_batch：funnel（MLE 附上的漏斗前段數字：資料庫總數、產業篩選後、網址有效、產品命中…，系統只顯示）
- v_recommendation 在最後面加上新欄位（CREATE OR REPLACE 只能往後加欄位，依賴它的 v_kpi_summary 不用重建）

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-18
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_RECOMMENDATION_BASE = """
SELECT c.company_id, c.tax_id, c.name, c.website_url, c.website_verified,
       c.status, c.owner_id, u.display_name AS owner_name, c.owner_locked_until,
       c.added_manually, c.updated_at,
       cl.run_id, cl.priority, COALESCE(p.stars, 0) AS stars, cl.score,
       cl.likelihood, COALESCE(cl.is_competitor, FALSE) AS is_competitor,
       COALESCE(c.industry_override_id, cl.industry_id) AS industry_id,
       i.name AS industry, cl.customer_type, cl.reason"""

_FROM = """
FROM company c
LEFT JOIN classification cl ON cl.company_id = c.company_id AND cl.is_current
LEFT JOIN dim_priority  p  ON p.priority = cl.priority
LEFT JOIN dim_industry  i  ON i.industry_id = COALESCE(c.industry_override_id, cl.industry_id)
LEFT JOIN app_user      u  ON u.user_id = c.owner_id"""

_NEW_COLUMNS = """,
       c.country, c.url_status, c.source,
       COALESCE(cl.fit_stars, p.stars::numeric(2,1)) AS fit_stars,
       cl.product_type, COALESCE(cl.tags, '{}') AS tags"""


def upgrade() -> None:
    op.execute(f"""
ALTER TABLE company
    ADD COLUMN country    CHAR(2) NOT NULL DEFAULT 'TW' CONSTRAINT ck_company_country CHECK (country ~ '^[A-Z]{{2}}$'),
    ADD COLUMN url_status TEXT NOT NULL DEFAULT 'unchecked'
                          CONSTRAINT ck_company_url_status CHECK (url_status IN ('valid','invalid','unchecked')),
    ADD COLUMN source     TEXT;
CREATE INDEX idx_company_source ON company(source);

ALTER TABLE classification
    ADD COLUMN fit_stars    NUMERIC(2,1) CONSTRAINT ck_classification_fit_stars CHECK (fit_stars BETWEEN 1.0 AND 5.0),
    ADD COLUMN product_type TEXT,
    ADD COLUMN tags         TEXT[] NOT NULL DEFAULT '{{}}';

ALTER TABLE import_batch ADD COLUMN funnel JSONB;

CREATE OR REPLACE VIEW v_recommendation AS {_RECOMMENDATION_BASE}{_NEW_COLUMNS}{_FROM};
""")


def downgrade() -> None:
    op.execute(f"""
DROP VIEW v_kpi_summary;
DROP VIEW v_recommendation;
CREATE VIEW v_recommendation AS {_RECOMMENDATION_BASE}{_FROM};
CREATE VIEW v_kpi_summary AS
SELECT k.*,
       CASE WHEN k.sent_total >= 10 THEN round(k.replied_total::numeric / k.sent_total, 4) END AS reply_rate
FROM (
  SELECT
    (SELECT count(*) FROM company WHERE status = 'pending_review')                 AS pending_review,
    (SELECT count(*) FROM company)                                                 AS total_companies,
    (SELECT count(*) FROM v_recommendation WHERE stars = 5)                        AS five_star,
    (SELECT count(*) FROM email_message WHERE sent_at >= now() - interval '7 days') AS sent_7d,
    (SELECT count(*) FROM email_message)                                           AS sent_total,
    (SELECT count(DISTINCT message_id) FROM email_event WHERE event_type = 'replied') AS replied_total
) k;
ALTER TABLE import_batch DROP COLUMN funnel;
ALTER TABLE classification DROP COLUMN tags, DROP COLUMN product_type, DROP COLUMN fit_stars;
DROP INDEX idx_company_source;
ALTER TABLE company DROP COLUMN source, DROP COLUMN url_status, DROP COLUMN country;
""")
