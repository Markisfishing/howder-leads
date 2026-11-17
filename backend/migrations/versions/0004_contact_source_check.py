"""0004 聯絡人來源加上 CHECK（M2-01a，SPEC 9 個資：聯絡人要記錄來源）

固定選項用 CHECK 約束，不只靠前端檢查（CLAUDE.md 第 5 節第 3 點）。
- website：從公司官網找到
- business_card：名片
- referral：別人介紹
- exhibition：展覽
- manual：業務手動輸入（其他管道）

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE contact
    ADD CONSTRAINT ck_contact_source
    CHECK (source IN ('website', 'business_card', 'referral', 'exhibition', 'manual'));
""")


def downgrade() -> None:
    op.execute("ALTER TABLE contact DROP CONSTRAINT IF EXISTS ck_contact_source;")
