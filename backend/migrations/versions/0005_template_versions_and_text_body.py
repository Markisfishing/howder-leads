"""0005 模板版本與純文字內文（M2-02、M2-05）

- email_template.family_id：同一份模板的各版本共用一個 family_id（第一版的 template_id）。
  修改模板就新增一列、版本 +1，舊版 is_active = false 保留下來，已產生的草稿可以對照。
  每個 family 同時只有一個啟用中的版本（部分唯一索引）。
- body_text：模板與草稿的內文改成由業務編輯純文字，系統再轉成 HTML 存在 body_html。
  這樣業務不用碰 HTML，預覽也不會執行使用者輸入的 HTML。

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-17
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE email_template
    ADD COLUMN family_id BIGINT REFERENCES email_template(template_id),
    ADD COLUMN body_text TEXT NOT NULL DEFAULT '';
UPDATE email_template SET family_id = template_id WHERE family_id IS NULL;
ALTER TABLE email_template ALTER COLUMN body_text DROP DEFAULT;
CREATE UNIQUE INDEX uq_template_active_version ON email_template(family_id) WHERE is_active;
CREATE UNIQUE INDEX uq_template_family_version ON email_template(family_id, version);

ALTER TABLE email_draft ADD COLUMN body_text TEXT NOT NULL DEFAULT '';
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE email_draft DROP COLUMN IF EXISTS body_text;
DROP INDEX IF EXISTS uq_template_family_version;
DROP INDEX IF EXISTS uq_template_active_version;
ALTER TABLE email_template DROP COLUMN IF EXISTS body_text,
                           DROP COLUMN IF EXISTS family_id;
""")
