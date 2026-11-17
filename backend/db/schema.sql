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
    rows_unchanged INT NOT NULL DEFAULT 0,
    model_name    TEXT,                              -- 確認匯入時建立 model_run 用
    payload       JSONB,                             -- 預覽時解析好的資料列，確認匯入時才寫入正式表
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
    industry_override_id SMALLINT REFERENCES dim_industry(industry_id), -- 業務修正的產業（優先於模型結果）
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
    source        TEXT NOT NULL
                  CONSTRAINT ck_contact_source
                  CHECK (source IN ('website','business_card','referral','exhibition','manual')),  -- 0004
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
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    family_id     BIGINT REFERENCES email_template(template_id),  -- 0005：同一份模板的各版本共用
    body_text     TEXT NOT NULL                      -- 0005：業務編輯的純文字，body_html 由它轉出
);
CREATE UNIQUE INDEX uq_template_active_version ON email_template(family_id) WHERE is_active;  -- 0005
CREATE UNIQUE INDEX uq_template_family_version ON email_template(family_id, version);        -- 0005

CREATE TYPE gen_mode AS ENUM ('template_only', 'template_ai', 'full_ai');

CREATE TABLE campaign (
    campaign_id   BIGSERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    template_id   BIGINT REFERENCES email_template(template_id),
    gen_mode      gen_mode NOT NULL DEFAULT 'template_ai',
    owner_id      BIGINT NOT NULL REFERENCES app_user(user_id),
    status        TEXT NOT NULL DEFAULT 'draft'
                  CONSTRAINT ck_campaign_status
                  CHECK (status IN ('draft','generating','reviewing','scheduled','sending','done')),  -- 0003
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
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    scheduled_at    TIMESTAMPTZ,                     -- 0003：排程寄出時間
    send_attempts   INT NOT NULL DEFAULT 0 CHECK (send_attempts >= 0),  -- 0003
    last_error      TEXT,                            -- 0003：錯誤代碼，不放信件內容
    body_text       TEXT NOT NULL DEFAULT ''         -- 0005：業務編輯的純文字，body_html 由它轉出
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
CREATE INDEX idx_message_sender_sent ON email_message(sender_id, sent_at);  -- 0003：每日上限

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
-- 0006：案件（每封開發信或「加入追蹤」一件，ADR 0004）；同一家公司同時只有一件未結案
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

CREATE TABLE case_update (                           -- 0006：業務人工回填；系統事件 channel = 'system'
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

-- ---------- Outlook 寄信權杖（0003，ADR 0005）----------
CREATE TABLE user_mail_credential (
    user_id       BIGINT PRIMARY KEY REFERENCES app_user(user_id) ON DELETE CASCADE,
    token_cache   BYTEA NOT NULL,                       -- Fernet 加密後的 MSAL 快取
    scopes        TEXT[] NOT NULL,
    status        TEXT NOT NULL DEFAULT 'connected' CHECK (status IN ('connected', 'needs_reconnect')),
    connected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at  TIMESTAMPTZ,
    last_error    TEXT
);

-- ---------- 背景工作佇列（0003，ADR 0003）----------
CREATE TABLE job (
    job_id        BIGSERIAL PRIMARY KEY,
    kind          TEXT NOT NULL CHECK (kind IN ('generate_drafts', 'send_email')),
    payload       JSONB NOT NULL DEFAULT '{}'::jsonb,
    status        TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    run_after     TIMESTAMPTZ NOT NULL DEFAULT now(),   -- 排程與重試退避
    attempts      INT NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts  INT NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
    last_error    TEXT,
    locked_at     TIMESTAMPTZ,
    locked_by     TEXT,
    created_by    BIGINT REFERENCES app_user(user_id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ
);
CREATE INDEX idx_job_ready ON job(run_after) WHERE status = 'queued';

CREATE FUNCTION notify_job_queued() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('job_queued', NEW.kind);   -- 叫醒 worker（LISTEN job_queued）
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_job_queued
AFTER INSERT ON job
FOR EACH ROW WHEN (NEW.status = 'queued')
EXECUTE FUNCTION notify_job_queued();

-- ---------- 指標層：KPI 只在這裡定義一次 ----------
CREATE VIEW v_recommendation AS                     -- 推薦清單：產業以業務修正為優先
SELECT c.company_id, c.tax_id, c.name, c.website_url, c.website_verified,
       c.status, c.owner_id, u.display_name AS owner_name, c.owner_locked_until,
       c.added_manually, c.updated_at,
       cl.run_id, cl.priority, COALESCE(p.stars, 0) AS stars, cl.score,
       cl.likelihood, COALESCE(cl.is_competitor, FALSE) AS is_competitor,
       COALESCE(c.industry_override_id, cl.industry_id) AS industry_id,
       i.name AS industry, cl.customer_type, cl.reason
FROM company c
LEFT JOIN classification cl ON cl.company_id = c.company_id AND cl.is_current
LEFT JOIN dim_priority  p  ON p.priority = cl.priority
LEFT JOIN dim_industry  i  ON i.industry_id = COALESCE(c.industry_override_id, cl.industry_id)
LEFT JOIN app_user      u  ON u.user_id = c.owner_id;

CREATE VIEW v_kpi_summary AS                        -- 推薦清單頁上方的 KPI 卡（比例也在這裡算，0002 加入 reply_rate）
SELECT k.*,
       CASE WHEN k.sent_total >= 10 THEN round(k.replied_total::numeric / k.sent_total, 4) END AS reply_rate
FROM (
  SELECT
    (SELECT count(*) FROM company WHERE status = 'pending_review')                 AS pending_review,
    (SELECT count(*) FROM company)                                                 AS total_companies,
    (SELECT count(*) FROM v_recommendation WHERE stars = 5)                        AS five_star,
    (SELECT count(*) FROM email_message WHERE sent_at >= now() - interval '7 days') AS sent_7d,
    (SELECT count(*) FROM email_message)                                           AS sent_total,
    (SELECT count(DISTINCT message_id) FROM email_event WHERE event_type = 'replied') AS replied_total
) k;

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

CREATE VIEW v_case_reminder AS                      -- 0007：待辦提醒（F-CASE-3），條件只在這裡定義
WITH c AS (
  SELECT sc.case_id, sc.owner_id, sc.company_id, sc.status, sc.next_follow_up,
         coalesce((SELECT max(u.created_at) FROM case_update u
                   WHERE u.case_id = sc.case_id AND u.result = 'sent'), sc.opened_at) AS last_sent_at
  FROM sales_case sc
  WHERE sc.closed_at IS NULL
)
SELECT case_id, owner_id, company_id, 'overdue_report'::text AS kind, last_sent_at AS since
FROM c WHERE status = 'sent' AND last_sent_at <= now() - interval '7 days'
UNION ALL
SELECT case_id, owner_id, company_id, 'follow_up_due', next_follow_up::timestamptz
FROM c WHERE next_follow_up IS NOT NULL AND next_follow_up <= ((now() AT TIME ZONE 'UTC') + interval '8 hours')::date  -- 台灣日期（無日光節約）
UNION ALL
SELECT case_id, owner_id, company_id, 'no_response', last_sent_at
FROM c WHERE status = 'no_response';

-- ---------- 種子資料 ----------
INSERT INTO dim_priority VALUES
 ('A','第一優先','整機控制、配電、線束或設備配線，端子台使用機率高','優先開發',5),
 ('B','可開發','可能使用，但要確認產品是否含控制箱/電控/線束','可開發',4),
 ('C','觀察／策略','需求不明確需再確認；或本身做連接器/端子台，以 OEM/合作角度接觸','觀察／策略',2),
 ('D','暫不優先','產品偏材料、純零件、加工，端子台非主要 BOM','暫不優先',1);

INSERT INTO dim_industry (name, is_prospect) VALUES
 ('工業自動化與機械設備', TRUE),
 ('電源、能源與充電設備', TRUE),
 ('配電盤與電機控制', TRUE),
 ('測試、量測與分析儀器', TRUE),
 ('消防、廣播與音響設備', TRUE),
 ('智慧建築、保全與門禁', TRUE),
 ('交通、車用與軌道設備', TRUE),
 ('空調、通風與家電控制', TRUE),
 ('醫療與牙科設備', TRUE),
 ('照明、LED與顯示設備', TRUE),
 ('通訊、RFID與物聯網', TRUE),
 ('電腦、伺服器與資訊設備', TRUE),
 ('半導體、PCB與電子製造設備', TRUE),
 ('馬達、變壓器與電力設備', TRUE),
 ('電子連接器、線材與EMS', TRUE),
 ('金屬、模具與塑膠零件製造', TRUE),
 ('電子零件通路與貿易', TRUE),
 ('其他商用與消費設備', TRUE),
 ('不是潛在客戶（不屬於任何一類）', FALSE);
