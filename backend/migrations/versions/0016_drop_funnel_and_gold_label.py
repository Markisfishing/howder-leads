"""0016 移除沒在用的 import_batch.funnel 與 gold_label 表（2026-11-18 使用者決定）

- import_batch.funnel：漏斗前段數字原本由 API 匯入附上；F-IMP-5 移除後沒有來源。
- gold_label：盲標已取消（M4-04 刪除），沒有任何程式讀寫。
downgrade 只還原結構，不還原資料（兩者都沒有資料來源）。

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-18
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE import_batch DROP COLUMN funnel;
DROP TABLE gold_label;
""")


def downgrade() -> None:
    op.execute("""
CREATE TABLE gold_label (
    company_id    BIGINT PRIMARY KEY REFERENCES company(company_id) ON DELETE CASCADE,
    industry_id   SMALLINT REFERENCES dim_industry(industry_id),
    is_prospect   BOOLEAN,
    correct_url   TEXT,
    labeler_id    BIGINT REFERENCES app_user(user_id),
    labeled_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE import_batch ADD COLUMN funnel JSONB;
""")
