"""0015 官網摘要：company_site_summary 表；job.kind 加 fetch_site（M4-08a、SPEC 7.4）

匯入確認後（或業務修正官網後）由 worker 抓官網、用本機 LLM 摘要，給 AI 寫信當公司背景。
只存「公司產品與產業描述」；人名、email、電話不存（寫入前由 domain 規則過濾）。
抓不到或沒有官網時 status = failed 並記錄錯誤代碼，寫信時改用推薦理由，不擋產生草稿。

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-18
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE company_site_summary (
    company_id   BIGINT PRIMARY KEY REFERENCES company(company_id) ON DELETE CASCADE,
    source_url   TEXT,                                   -- 實際抓取的首頁網址
    summary      TEXT,
    status       TEXT NOT NULL
                 CONSTRAINT ck_site_summary_status CHECK (status IN ('ok', 'failed')),
    error_code   TEXT,                                   -- 失敗時的錯誤代碼，不放網頁內容
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_site_summary_consistent
        CHECK ((status = 'ok' AND summary IS NOT NULL AND error_code IS NULL)
            OR (status = 'failed' AND summary IS NULL AND error_code IS NOT NULL))
);

ALTER TABLE job DROP CONSTRAINT job_kind_check;
ALTER TABLE job ADD CONSTRAINT job_kind_check
    CHECK (kind IN ('generate_drafts', 'send_email', 'case_daily', 'classify_reply', 'fetch_site'));
""")


def downgrade() -> None:
    op.execute("""
DELETE FROM job WHERE kind = 'fetch_site';
ALTER TABLE job DROP CONSTRAINT job_kind_check;
ALTER TABLE job ADD CONSTRAINT job_kind_check
    CHECK (kind IN ('generate_drafts', 'send_email', 'case_daily', 'classify_reply'));

DROP TABLE company_site_summary;
""")
