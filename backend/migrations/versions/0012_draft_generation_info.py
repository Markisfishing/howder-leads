"""0012 email_draft 記錄是哪個 provider、模型、prompt 版本產生的（M4-06h、F-MAIL-8、ADR 0006）

模板代入（template_only）沒有用到 AI，三個欄位留空；AI 產生的草稿才會填，
這樣之後才能比較不同模型與 prompt 版本的品質（改稿幅度 edit_ratio）。

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-18
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE email_draft
    ADD COLUMN gen_provider    TEXT,
    ADD COLUMN gen_model       TEXT,
    ADD COLUMN prompt_version  TEXT;
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE email_draft
    DROP COLUMN prompt_version,
    DROP COLUMN gen_model,
    DROP COLUMN gen_provider;
""")
