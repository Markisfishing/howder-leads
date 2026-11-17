-- =====================================================================
-- 厚達電子 潛在客戶推薦與邀請信系統 — 資料庫 Schema (PostgreSQL 16)
-- 規格說明見 docs/SPEC.md 第 8 節
-- 原則：所有表用 company_id 串接；company.tax_id(統編) 為業務上的唯一鍵
-- =====================================================================

-- ---------- 使用者與權限 ----------
CREATE TYPE user_role AS ENUM ('sales', 'manager', 'admin');

CREATE TABLE app_user (
    user_id       BIGSERIAL PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,              -- 公司 Microsoft 帳號
    display_name  TEXT NOT NULL,
    role          user_role NOT NULL DEFAULT 'sales',
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- 維度表 ----------
CREATE TABLE dim_industry (                          -- 18 類標準化產業
    industry_id   SMALLSERIAL PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    is_prospect   BOOLEAN NOT NULL DEFAULT TRUE      -- 「不是潛在客戶」那一類為 FALSE
);

CREATE TABLE dim_priority (                          -- 取代 Excel 裡混在資料欄的圖例
    priority          CHAR(1) PRIMARY KEY CHECK (priority IN ('A','B','C','D')),
    label             TEXT NOT NULL,                 -- 第一優先 / 可開發 / 觀察 / 暫不優先
    definition        TEXT NOT NULL,
    suggested_action  TEXT NOT NULL,
    stars             SMALLINT NOT NULL CHECK (stars BETWEEN 1 AND 5)
);

-- ---------- 名單與匯入 ----------
CREATE TABLE import_batch (
    batch_id      BIGSERIAL PRIMARY KEY,
    file_name     TEXT,
    source        TEXT NOT NULL DEFAULT 'csv',        -- csv | api
    run_id        BIGINT,                            -- 對應的模型版本（可為空）
    rows_total    INT NOT NULL DEFAULT 0,
    rows_created  INT NOT NULL DEFAULT 0,
    rows_updated  INT NOT NULL DEFAULT 0,
    rows_error    INT NOT NULL DEFAULT 0,
    error_report  JSONB,
    imported_by   BIGINT REFERENCES app_user(user_id),
    status        TEXT NOT NULL DEFAULT 'previewed', -- previewed | committed | cancelled
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TYPE company_status AS ENUM (
    'imported', 'pending_review', 'approved', 'rejected',
    'drafted', 'draft_approved', 'sent', 'replied',
    'meeting', 'won', 'lost', 'do_not_contact'
);

CREATE TABLE company (
    company_id           BIGSERIAL PRIMARY KEY,
    tax_id               CHAR(8) NOT NULL UNIQUE,    -- 統編
    name                 TEXT NOT NULL,
    registered_products  TEXT,                       -- 工廠登記產品
    website_url          TEXT,
    website_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    status               company_status NOT NULL DEFAULT 'pending_review',
    owner_id             BIGINT REFERENCES app_user(user_id),  -- 負責業務（鎖定用）
    owner_locked_until   TIMESTAMPTZ,
    added_manually       BOOLEAN NOT NULL DEFAULT FALSE,       -- 業務自行加入 = 模型漏掉的
    first_batch_id       BIGINT REFERENCES import_batch(batch_id),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_company_status ON company(status);
CREATE INDEX idx_company_owner  ON company(owner_id);

-- ---------- 模型輸出（每次 run 保留版本）----------
CREATE TABLE model_run (
    run_id          BIGSERIAL PRIMARY KEY,
    model_name      TEXT NOT NULL,
    prompt_version  TEXT,
    params          JSONB,
    cost_tokens     BIGINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE import_batch ADD CONSTRAINT fk_batch_run FOREIGN KEY (run_id) REFERENCES model_run(run_id);

CREATE TABLE classification (
    classification_id  BIGSERIAL PRIMARY KEY,
    company_id         BIGINT NOT NULL REFERENCES company(company_id) ON DELETE CASCADE,
    run_id             BIGINT NOT NULL REFERENCES model_run(run_id),
    industry_id        SMALLINT REFERENCES dim_industry(industry_id),
    customer_type      TEXT,                           -- 客戶屬性
    likelihood         TEXT CHECK (likelihood IN ('高','中','低')),
    is_competitor      BOOLEAN NOT NULL DEFAULT FALSE, -- 原「明確但競合」拆出來
    priority           CHAR(1) REFERENCES dim_priority(priority),
    score              NUMERIC(5,2) CHECK (score BETWEEN 0 AND 100),
    reason             TEXT,                           -- 判斷理由
    is_current         BOOLEAN NOT NULL DEFAULT TRUE,  -- 每家公司只有一筆 current
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, run_id)
);
CREATE UNIQUE INDEX uq_classification_current ON classification(company_id) WHERE is_current;

-- ---------- 業務審核（回饋給 MLE）----------
CREATE TABLE review (
    review_id       BIGSERIAL PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES company(company_id) ON DELETE CASCADE,
    reviewer_id     BIGINT NOT NULL REFERENCES app_user(user_id),
    decision        TEXT NOT NULL CHECK (decision IN ('approved','rejected')),
    reject_reason   TEXT CHECK (reject_reason IN
                      ('wrong_industry','existing_customer','competitor',
                       'wrong_website','no_demand','closed_business','other')),
    corrected_industry_id  SMALLINT REFERENCES dim_industry(industry_id),
    corrected_url   TEXT,
    note            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (decision = 'approved' OR reject_reason IS NOT NULL)  -- 排除一定要有原因
);

-- 盲標用的標準答案（標註員看不到模型結果）
CREATE TABLE gold_label (
    company_id    BIGINT PRIMARY KEY REFERENCES company(company_id) ON DELETE CASCADE,
    industry_id   SMALLINT REFERENCES dim_industry(industry_id),
    is_prospect   BOOLEAN,
    correct_url   TEXT,
    labeler_id    BIGINT REFERENCES app_user(user_id),
    labeled_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- 聯絡人 ----------
CREATE TABLE contact (
    contact_id    BIGSERIAL PRIMARY KEY,
    company_id    BIGINT NOT NULL REFERENCES company(company_id) ON DELETE CASCADE,
    name          TEXT,
    title         TEXT,
    email         TEXT NOT NULL,
    source        TEXT NOT NULL,                     -- website | manual | business_card ...
    is_verified   BOOLEAN NOT NULL DEFAULT FALSE,
    unsubscribed  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, email)
);

-- ---------- 郵件 ----------
CREATE TABLE email_template (
    template_id   BIGSERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    language      TEXT NOT NULL DEFAULT 'zh-TW',
    subject       TEXT NOT NULL,                     -- 可含 {{company_name}} 等變數
    body_html     TEXT NOT NULL,                     -- 可含 {{ai_paragraph}} 插槽
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    version       INT NOT NULL DEFAULT 1,
    created_by    BIGINT REFERENCES app_user(user_id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TYPE gen_mode AS ENUM ('template_only', 'template_ai', 'full_ai');

CREATE TABLE campaign (
    campaign_id   BIGSERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    template_id   BIGINT REFERENCES email_template(template_id),
    gen_mode      gen_mode NOT NULL DEFAULT 'template_ai',
    owner_id      BIGINT NOT NULL REFERENCES app_user(user_id),
    status        TEXT NOT NULL DEFAULT 'draft',    -- draft | reviewing | scheduled | sending | done
    scheduled_at  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TYPE draft_status AS ENUM ('generating','pending_review','approved','discarded','sent','failed');

CREATE TABLE email_draft (
    draft_id        BIGSERIAL PRIMARY KEY,
    campaign_id     BIGINT NOT NULL REFERENCES campaign(campaign_id) ON DELETE CASCADE,
    company_id      BIGINT NOT NULL REFERENCES company(company_id),
    contact_id      BIGINT NOT NULL REFERENCES contact(contact_id),
    subject         TEXT NOT NULL,
    body_html       TEXT NOT NULL,                   -- 業務最後確認的版本
    ai_original     TEXT,                            -- AI 原稿（量測業務改了多少）
    edit_ratio      NUMERIC(4,3),                    -- 0 = 沒改，1 = 全部重寫
    status          draft_status NOT NULL DEFAULT 'generating',
    approved_by     BIGINT REFERENCES app_user(user_id),
    approved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_draft_campaign_status ON email_draft(campaign_id, status);

CREATE TABLE email_message (                        -- 實際寄出的信
    message_id        BIGSERIAL PRIMARY KEY,
    draft_id          BIGINT NOT NULL UNIQUE REFERENCES email_draft(draft_id),
    sender_id         BIGINT NOT NULL REFERENCES app_user(user_id),
    graph_message_id  TEXT,                          -- Microsoft Graph 的 id
    conversation_id   TEXT,                          -- 用來比對回覆
    sent_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE email_event (
    event_id      BIGSERIAL PRIMARY KEY,
    message_id    BIGINT NOT NULL REFERENCES email_message(message_id) ON DELETE CASCADE,
    event_type    TEXT NOT NULL CHECK (event_type IN
                    ('delivered','opened','clicked','replied','bounced','unsubscribed')),
    sentiment     TEXT CHECK (sentiment IN ('positive','neutral','negative')),  -- 回覆分類
    payload       JSONB,
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_event_message ON email_event(message_id, event_type);

-- ---------- 商機與活動紀錄 ----------
CREATE TABLE opportunity (
    opp_id        BIGSERIAL PRIMARY KEY,
    company_id    BIGINT NOT NULL REFERENCES company(company_id),
    owner_id      BIGINT NOT NULL REFERENCES app_user(user_id),
    stage         TEXT NOT NULL CHECK (stage IN ('contacted','meeting','quote','sample','won','lost')),
    amount_twd    NUMERIC(14,0),
    closed_at     TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE activity_log (                         -- 稽核 + 業務備註，所有狀態變更都寫一筆
    log_id        BIGSERIAL PRIMARY KEY,
    company_id    BIGINT REFERENCES company(company_id),
    user_id       BIGINT REFERENCES app_user(user_id),
    action        TEXT NOT NULL,                     -- status_change | note | import | send ...
    from_value    TEXT,
    to_value      TEXT,
    note          TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_log_company ON activity_log(company_id, created_at DESC);

-- ---------- 指標層：KPI 只在這裡定義一次 ----------
CREATE VIEW v_recommendation AS
SELECT c.company_id, c.tax_id, c.name, c.website_url, c.status, c.owner_id,
       cl.priority, p.stars, cl.score, cl.likelihood, cl.is_competitor,
       i.name AS industry, cl.customer_type, cl.reason
FROM company c
LEFT JOIN classification cl ON cl.company_id = c.company_id AND cl.is_current
LEFT JOIN dim_priority  p  ON p.priority = cl.priority
LEFT JOIN dim_industry  i  ON i.industry_id = cl.industry_id;

CREATE VIEW v_funnel AS
SELECT status, count(*) AS companies FROM company GROUP BY status;

CREATE VIEW v_win_rate_by_priority AS               -- 驗證評分：應 A > B > C > D
SELECT cl.priority,
       count(*) FILTER (WHERE c.status IN ('sent','replied','meeting','won','lost')) AS contacted,
       count(*) FILTER (WHERE c.status IN ('replied','meeting','won'))              AS replied,
       count(*) FILTER (WHERE c.status = 'won')                                      AS won
FROM company c
JOIN classification cl ON cl.company_id = c.company_id AND cl.is_current
GROUP BY cl.priority;

CREATE VIEW v_reject_reasons AS                     -- 給 MLE 的回饋
SELECT r.reject_reason, cl.run_id, count(*) AS n
FROM review r
JOIN classification cl ON cl.company_id = r.company_id AND cl.is_current
WHERE r.decision = 'rejected'
GROUP BY r.reject_reason, cl.run_id;

-- ---------- 種子資料 ----------
INSERT INTO dim_priority VALUES
 ('A','第一優先','整機控制、配電、線束或設備配線，端子台使用機率高','優先開發',5),
 ('B','可開發','可能使用，但要確認產品是否含控制箱/電控/線束','可開發',4),
 ('C','觀察／策略','需求不明確需再確認；或本身做連接器/端子台，以 OEM/合作角度接觸','觀察／策略',2),
 ('D','暫不優先','產品偏材料、純零件、加工，端子台非主要 BOM','暫不優先',1);
