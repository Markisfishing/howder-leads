"""0006 案件 sales_case 與回填 case_update（M3-07a、ADR 0004、F-CASE-1、F-CASE-2）

- opportunity 從 M1 建好後沒有任何程式寫入（商機併入案件，F-TRK-4），直接刪掉改建 sales_case。
- 每封開發信（或「加入追蹤」）開一件案件，編號 C-0001 由 case_id 產生（generated column）。
- 同一家公司同時只能有一件未結案的案件（部分唯一索引），之後再寄信就加在同一件的時間軸。
- case_update 是業務人工回填的紀錄（ADR 0004：系統不讀業務信箱），系統自動事件用 channel = 'system'。
- 聯絡人做個資刪除時，案件與回填的 contact_id 改成 NULL（案件本身是業務紀錄，留著）。

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-18
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
DROP TABLE opportunity;

CREATE TABLE sales_case (
    case_id          BIGSERIAL PRIMARY KEY,
    case_no          TEXT GENERATED ALWAYS AS ('C-' || lpad(case_id::text, 4, '0')) STORED,
    company_id       BIGINT NOT NULL REFERENCES company(company_id),
    contact_id       BIGINT REFERENCES contact(contact_id) ON DELETE SET NULL,
    owner_id         BIGINT NOT NULL REFERENCES app_user(user_id),
    origin           TEXT NOT NULL CONSTRAINT ck_case_origin CHECK (origin IN ('email','tracking')),
    message_id       BIGINT REFERENCES email_message(message_id) ON DELETE SET NULL,
    status           TEXT NOT NULL
                     CONSTRAINT ck_case_status
                     CHECK (status IN ('sent','tracking','replied','negotiating','no_response','won','lost')),
    opened_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_update_at   TIMESTAMPTZ,
    next_follow_up   DATE,
    amount_twd       NUMERIC(14,0) CONSTRAINT ck_case_amount CHECK (amount_twd IS NULL OR amount_twd >= 0),
    closed_at        TIMESTAMPTZ,
    CONSTRAINT ck_case_closed CHECK ((status IN ('won','lost')) = (closed_at IS NOT NULL))
);
CREATE UNIQUE INDEX uq_case_open_per_company ON sales_case(company_id) WHERE closed_at IS NULL;
CREATE INDEX idx_case_owner_status ON sales_case(owner_id, status);

CREATE TABLE case_update (
    update_id        BIGSERIAL PRIMARY KEY,
    case_id          BIGINT NOT NULL REFERENCES sales_case(case_id),
    user_id          BIGINT REFERENCES app_user(user_id),
    channel          TEXT NOT NULL
                     CONSTRAINT ck_update_channel
                     CHECK (channel IN ('email','line','wechat','phone','visit','other','system')),
    contact_id       BIGINT REFERENCES contact(contact_id) ON DELETE SET NULL,
    result           TEXT NOT NULL
                     CONSTRAINT ck_update_result
                     CHECK (result IN ('sent','replied','negotiating','won','lost','no_response')),
    note             TEXT,
    next_follow_up   DATE,
    amount_twd       NUMERIC(14,0) CONSTRAINT ck_update_amount CHECK (amount_twd IS NULL OR amount_twd >= 0),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_case_update_case ON case_update(case_id, created_at);
""")


def downgrade() -> None:
    op.execute("""
DROP TABLE IF EXISTS case_update;
DROP TABLE IF EXISTS sales_case;
CREATE TABLE opportunity (
    opp_id        BIGSERIAL PRIMARY KEY,
    company_id    BIGINT NOT NULL REFERENCES company(company_id),
    owner_id      BIGINT NOT NULL REFERENCES app_user(user_id),
    stage         TEXT NOT NULL CHECK (stage IN ('contacted','meeting','quote','sample','won','lost')),
    amount_twd    NUMERIC(14,0),
    closed_at     TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
""")
