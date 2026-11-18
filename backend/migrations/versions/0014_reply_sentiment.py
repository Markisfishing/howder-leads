"""0014 回覆態度：case_update 加 sentiment／sentiment_source；job.kind 加 classify_reply（M4-07a、F-TRK-2）

回填有備註時，worker 用 LLM 判斷客戶態度（positive／neutral／negative，source = ai）；
業務可以手動修正（source = manual）。判斷失敗不影響回填本身，sentiment 留空。

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-18
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE case_update
    ADD COLUMN sentiment        TEXT CONSTRAINT ck_case_update_sentiment
                                CHECK (sentiment IN ('positive', 'neutral', 'negative')),
    ADD COLUMN sentiment_source TEXT CONSTRAINT ck_case_update_sentiment_source
                                CHECK (sentiment_source IN ('ai', 'manual')),
    ADD CONSTRAINT ck_case_update_sentiment_pair CHECK ((sentiment IS NULL) = (sentiment_source IS NULL));

ALTER TABLE job DROP CONSTRAINT job_kind_check;
ALTER TABLE job ADD CONSTRAINT job_kind_check
    CHECK (kind IN ('generate_drafts', 'send_email', 'case_daily', 'classify_reply'));
""")


def downgrade() -> None:
    op.execute("""
DELETE FROM job WHERE kind = 'classify_reply';
ALTER TABLE job DROP CONSTRAINT job_kind_check;
ALTER TABLE job ADD CONSTRAINT job_kind_check
    CHECK (kind IN ('generate_drafts', 'send_email', 'case_daily'));

ALTER TABLE case_update
    DROP CONSTRAINT ck_case_update_sentiment_pair,
    DROP COLUMN sentiment_source,
    DROP COLUMN sentiment;
""")
