"""0003 背景工作佇列、Outlook 寄信權杖、寄送欄位

- job：PostgreSQL 佇列（ADR 0003）。worker 用 SELECT … FOR UPDATE SKIP LOCKED 領工作，
  新增工作時用 NOTIFY job_queued 叫醒 worker。
- user_mail_credential：每位業務一筆加密後的 MSAL 權杖快取（ADR 0005）。
- email_draft：排程時間、寄送嘗試次數、最後錯誤（F-MAIL-6、SPEC 9 可用性）。
- campaign.status：補上 CHECK（CLAUDE.md 第 5 節第 3 點）。
- email_message：依寄件人與時間建索引，算每日上限用。

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE job (
    job_id        BIGSERIAL PRIMARY KEY,
    kind          TEXT NOT NULL CHECK (kind IN ('generate_drafts', 'send_email')),
    payload       JSONB NOT NULL DEFAULT '{}'::jsonb,
    status        TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    run_after     TIMESTAMPTZ NOT NULL DEFAULT now(),   -- 排程與重試退避
    attempts      INT NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts  INT NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
    last_error    TEXT,                                 -- 錯誤代碼與簡述，不放信件內容或權杖
    locked_at     TIMESTAMPTZ,                          -- worker 領走的時間，逾時可回收
    locked_by     TEXT,
    created_by    BIGINT REFERENCES app_user(user_id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ
);
CREATE INDEX idx_job_ready ON job(run_after) WHERE status = 'queued';

CREATE FUNCTION notify_job_queued() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('job_queued', NEW.kind);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_job_queued
AFTER INSERT ON job
FOR EACH ROW WHEN (NEW.status = 'queued')
EXECUTE FUNCTION notify_job_queued();

CREATE TABLE user_mail_credential (
    user_id       BIGINT PRIMARY KEY REFERENCES app_user(user_id) ON DELETE CASCADE,
    token_cache   BYTEA NOT NULL,                       -- Fernet 加密後的 MSAL 快取
    scopes        TEXT[] NOT NULL,
    status        TEXT NOT NULL DEFAULT 'connected' CHECK (status IN ('connected', 'needs_reconnect')),
    connected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at  TIMESTAMPTZ,
    last_error    TEXT
);

ALTER TABLE email_draft
    ADD COLUMN scheduled_at  TIMESTAMPTZ,
    ADD COLUMN send_attempts INT NOT NULL DEFAULT 0 CHECK (send_attempts >= 0),
    ADD COLUMN last_error    TEXT;

ALTER TABLE campaign
    ADD CONSTRAINT ck_campaign_status
    CHECK (status IN ('draft', 'generating', 'reviewing', 'scheduled', 'sending', 'done'));

CREATE INDEX idx_message_sender_sent ON email_message(sender_id, sent_at);
""")


def downgrade() -> None:
    op.execute("""
DROP INDEX IF EXISTS idx_message_sender_sent;
ALTER TABLE campaign DROP CONSTRAINT IF EXISTS ck_campaign_status;
ALTER TABLE email_draft DROP COLUMN IF EXISTS last_error,
                        DROP COLUMN IF EXISTS send_attempts,
                        DROP COLUMN IF EXISTS scheduled_at;
DROP TABLE IF EXISTS user_mail_credential;
DROP TRIGGER IF EXISTS trg_job_queued ON job;
DROP FUNCTION IF EXISTS notify_job_queued();
DROP TABLE IF EXISTS job;
""")
