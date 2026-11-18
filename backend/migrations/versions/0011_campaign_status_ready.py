"""0011 campaign.status 加上 ready（待寄出）（M2-16、F-MAIL-4）

草稿都審完、還沒按寄出時，批次顯示「待寄出」，不再停在「待審核」。

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-18
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE campaign DROP CONSTRAINT ck_campaign_status;
ALTER TABLE campaign ADD CONSTRAINT ck_campaign_status
    CHECK (status IN ('draft', 'generating', 'reviewing', 'ready', 'scheduled', 'sending', 'done'));
""")


def downgrade() -> None:
    op.execute("""
UPDATE campaign SET status = 'reviewing' WHERE status = 'ready';
ALTER TABLE campaign DROP CONSTRAINT ck_campaign_status;
ALTER TABLE campaign ADD CONSTRAINT ck_campaign_status
    CHECK (status IN ('draft', 'generating', 'reviewing', 'scheduled', 'sending', 'done'));
""")
