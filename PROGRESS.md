# 開發進度

> 這份檔案記錄「現在做到哪裡」。規格看 `docs/SPEC.md`，每個階段做了什麼看 `CHANGELOG.md`。
> 規則（CLAUDE.md 第 13 節）：每完成一個任務就把 `[ ]` 改成 `[x]`，並在行尾加上完成日期，同時更新下方的「最後更新」。

| 項目 | 狀態 |
|---|---|
| 最後更新 | 2026-11-18 |
| 目前階段 | **M3 完成**（sandbox 閉環示範通過）；M2 只剩 M2-15 真實 Outlook 驗收；M1 只剩 M1-03 Docker 驗證；M4 尚未拆細 |
| 下一個任務 | 把 M4 拆成和 M3 一樣細的任務（CLAUDE.md 第 13 節），從 M4-06 地端 LLM 寫信開始 |
| 卡住 / 待確認 | 寄信時要不要自動認領公司（見下方「開發中發現」）、優先級 C 的定義（SPEC 11-1）、Microsoft 365 管理員是否核准 `Mail.Send`（SPEC 11-4）、國外公司唯一鍵（SPEC 11-6）、星等算法由 MLE 提供（SPEC 11-7）、Docker Desktop 無法啟動（M1-03） |

格式：`- [ ] 編號 任務（需求 ID）` → 完成後 `- [x] 編號 任務（需求 ID） — YYYY-MM-DD`
一個任務的大小以「一次對話、一個 commit 做得完」為準；太大就拆開。

---

## M0 規劃與設計

- [x] M0-01 整理 50 家客戶 Excel 的欄位與資料問題 — 2026-11-17
- [x] M0-02 撰寫系統規格書 `docs/SPEC.md` — 2026-11-17
- [x] M0-03 設計資料庫 schema `backend/db/schema.sql` — 2026-11-17
- [x] M0-04 從厚達官網取品牌色，產出 `design-tokens.css`（磚紅主色、淺色底） — 2026-11-17
- [x] M0-05 推薦清單頁靜態原型（手機與桌機都檢查過） — 2026-11-17
- [x] M0-06 拆分 frontend / backend 資料夾，撰寫 `CLAUDE.md` 開發規則 — 2026-11-17
- [x] M0-07 git init，分段 commit — 2026-11-17
- [x] M0-08 建立 `PROGRESS.md` 與 `CHANGELOG.md` — 2026-11-17

## M1 MVP：匯入、推薦清單、審核

### 基礎建設
- [x] M1-01 建立後端專案骨架（uv、pyproject、`app/main.py`、`GET /health`） — 2026-11-17
- [x] M1-02 後端加上 ruff、mypy、pytest 設定，第一個測試 `test_health` — 2026-11-17
- [ ] M1-03 `docker-compose.yml`：postgres 16（開發用；依 ADR 0003 不再需要 redis）（進行中：已寫 docker-compose.yml，但 Docker Desktop 在這台電腦無法啟動、未驗證；開發與測試改用 backend/scripts/dev_db.py 內嵌 Postgres）
- [x] M1-04 `.env.example` 和設定讀取（pydantic-settings），包含 `MAIL_MODE=sandbox` — 2026-11-17
- [x] M1-05 導入 Alembic，把 `schema.sql` 轉成第一個 migration — 2026-11-17
- [x] M1-06 SQLAlchemy models（company、classification、review、dim_*、activity_log、import_batch、model_run、app_user） — 2026-11-17
- [x] M1-07 種子資料：`dim_industry` 18 類、`dim_priority` A–D — 2026-11-17
- [x] M1-08 統一錯誤格式 `{error:{code,message}}` 和例外處理 — 2026-11-17
- [x] M1-09 建立前端專案骨架（Vite + React + TS strict、ESLint、Vitest） — 2026-11-17
- [x] M1-10 前端引入 `design-tokens.css`，建立 `global.css` — 2026-11-17
- [x] M1-11 前端 `src/api/` 基礎 client（錯誤碼對應中文訊息） — 2026-11-17

### 登入與權限
- [x] M1-12 Microsoft Entra ID OIDC 登入（後端驗證 token） — 2026-11-17（後端驗證完成；尚未用真實租用戶測試，待 SPEC 11-4 權限核准）
- [x] M1-13 `GET /api/v1/me` 與 `app_user` 自動建立 — 2026-11-17
- [x] M1-14 角色權限檢查（sales / manager / admin）＋測試：業務不能呼叫 `/admin` — 2026-11-17
- [x] M1-15 前端登入流程與路由守衛 — 2026-11-17（dev 快速登入已驗證；Entra 登入流程已寫好，待真實租用戶測試）

### 名單匯入（F-IMP）
- [x] M1-16 `importer`：解析 CSV/XLSX，支援 UTF-8 / Big5（F-IMP-1） — 2026-11-17
- [x] M1-17 `importer`：欄位驗證（統編 8 碼、產業/優先級要在維度表裡）（F-IMP-4） — 2026-11-17
- [x] M1-18 `importer`：產生預覽差異（新增 / 更新 / 錯誤）（F-IMP-2） — 2026-11-17
- [x] M1-19 `importer`：確認寫入，以統編去重，建立 `model_run` 與 `classification`（F-IMP-3） — 2026-11-17
- [x] M1-20 Excel 欄位轉換規則（拆「明確但競合」、忽略圖例欄）（SPEC 8.3） — 2026-11-17
- [x] M1-21 `POST /imports`、`POST /imports/{id}/commit` API（F-IMP-2、F-IMP-5） — 2026-11-17
- [x] M1-22 前端 `/admin/imports` 上傳與預覽頁 — 2026-11-17

### 狀態機與審核
- [x] M1-23 `domain/state_machine.py`：合法轉換表＋單元測試（SPEC 3.1） — 2026-11-17（實際檔名為 `domain/company_rules.py`，狀態機與認領規則放在同一檔）
- [x] M1-24 狀態變更一律寫 `activity_log` — 2026-11-17
- [x] M1-25 `POST /reviews` 批次審核，排除一定要有原因（F-REC-3） — 2026-11-17
- [x] M1-26 認領與 30 天鎖定規則＋測試（SPEC 3.1） — 2026-11-17

### 推薦清單（F-REC）
- [x] M1-27 `GET /companies`：讀 `v_recommendation`，支援篩選、排序、分頁（F-REC-1、F-REC-2） — 2026-11-17
- [x] M1-28 `GET /companies/{id}`、`PATCH /companies/{id}`（F-REC-4） — 2026-11-17
- [x] M1-29 `POST /companies` 手動加入（F-REC-6） — 2026-11-17
- [x] M1-30 KPI API（讀 view）（F-REC-5） — 2026-11-17
- [x] M1-31 前端版面：側邊導覽列（照原型） — 2026-11-17
- [x] M1-32 前端推薦清單表格（星級、理由、狀態；四種狀態：載入／空／錯誤／正常） — 2026-11-17
- [x] M1-33 前端篩選列，篩選條件同步到網址（F-REC-2） — 2026-11-17
- [x] M1-34 前端 KPI 卡 — 2026-11-17
- [x] M1-35 前端批次動作列與「排除原因」對話框（F-REC-3） — 2026-11-17
- [x] M1-36 前端公司詳情側欄（修正官網與產業）（F-REC-4） — 2026-11-17
- [x] M1-37 前端手動加入公司（F-REC-6） — 2026-11-17

### 驗收
- [x] M1-38 用 50 家測試資料走完一輪：匯入 → 審核 → 匯出排除原因 — 2026-11-17（本機用原始 Excel 走過：49 家匯入、1 列缺統編被擋下；重複匯入 0 新增；資料只在本機資料庫，未進 repo）
- [x] M1-39 375px / 1280px 瀏覽器檢查、鍵盤操作檢查 — 2026-11-17（批次通過、排除對話框、側欄都可以只用鍵盤完成）

## M2 寄信：模板、預覽佇列、Graph 寄送

完成條件（SPEC 10）：一位業務從核准到寄出 10 封信，全部出現在他的 Outlook 寄件備份。
原本的 M2-01～08 太大，依 CLAUDE.md 第 13 節拆成 a、b、c…；子任務全部完成才勾原本那一行。新發現的工作從 M2-09 往後編。

### 先決定（會影響後面所有任務）
- [x] M2-09 ADR：背景工作佇列 — 2026-11-17（使用者決定改用 PostgreSQL 佇列，見 `docs/adr/0003`；CLAUDE.md、SPEC、docker-compose 已同步拿掉 Redis）
- [x] M2-10 ADR：Outlook 委派權杖。每位業務只授權 `Mail.Send`（ADR 0004 決定不申請 `Mail.Read`），後端加密存 refresh token，worker 用它代業務寄信（SPEC 7.5、9 安全） — 2026-11-17（見 `docs/adr/0005`：On-Behalf-Of＋Fernet 加密，一位業務一筆）
- [x] M2-11 migration 0003（單獨 commit），同步 `schema.sql` 和 SPEC 8.1： — 2026-11-17（另加 `NOTIFY job_queued` 觸發器與每日上限用的索引；13 個 `test_m2_11_*` 含 SKIP LOCKED、NOTIFY、退回再升級）
  - `email_draft` 加上 `scheduled_at`、`send_attempts`、`last_error`
  - `campaign.status` 加 CHECK
  - 新增 `user_mail_credential`（欄位依 ADR 0005）
  - 新增 `job` 佇列表（ADR 0003）

### 聯絡人
- [x] M2-01 聯絡人 CRUD（拆成下列 a、b） — 2026-11-17
  - [x] M2-01a 後端 `POST /contacts`、`PATCH /contacts/{id}`、標記退訂、個資刪除（真的刪除，連帶刪除郵件內容並寫 `activity_log`）。來源必填、email 格式檢查、同一家公司不重複（SPEC 9 個資） — 2026-11-17（migration 0004 來源 CHECK；退訂同時把公司改成 `do_not_contact`；刪除限主管／管理員且要填原因）
  - [x] M2-01b 前端：在公司詳情側欄新增、編輯、退訂、刪除聯絡人（刪除要再確認一次） — 2026-11-17（刪除要填原因並勾選「了解無法復原」，只有主管／管理員看得到）

### 模板
- [x] M2-02 郵件模板管理（拆成下列 a～c） — 2026-11-17
  - [x] M2-02a 後端 `/templates`（只有 admin） — 2026-11-17（migration 0005 加 `family_id` 與純文字 `body_text`；讀取所有人可用，寫入限 admin）
    - 修改時新增一個版本，舊版保留，已產生的草稿可以對照
    - 變數只能用白名單：`{{company_name}}`、`{{contact_name}}`、`{{sender_name}}`…
    - 存檔時檢查是否有退訂說明
  - [x] M2-02b 前端 `/admin/templates`：列表、編輯、用假資料即時預覽 — 2026-11-17
  - [x] M2-02c 初版模板種子（內容等 SPEC 11-5，先放佔位文字） — 2026-11-17（`uv run python -m scripts.seed_templates`）

### 產生草稿
- [x] M2-03 建立 campaign 與 `template_only` 草稿產生（F-MAIL-1、F-MAIL-2、F-MAIL-3；拆成下列 a～e） — 2026-11-18
  - [x] M2-03a `domain` 模板渲染純函式：代入變數、跳脫 HTML、缺變數就報錯、強制附上退訂說明 — 2026-11-17（`domain/template_rules.py`）
  - [x] M2-03b `POST /campaigns` — 2026-11-18
    - 只能選「已通過」而且自己能操作的公司，每家選一位聯絡人
    - 回傳 `job_id`
    - 公司狀態 `approved → drafted`
  - [x] M2-03c worker `generate_drafts`（`template_only`） — 2026-11-18
    - 單封失敗不影響其他封
    - `GET /campaigns/{id}` 回傳產生進度
    - 一開始產生的內文存進 `ai_original`，給 F-MAIL-8 比對
  - [x] M2-03d 前端 `/campaigns/new` — 2026-11-18
    - 從已通過名單選對象 → 選模板
    - 生成模式只開放 `template_only`，AI 模式顯示「M4 開放」
    - 顯示被防呆排除的公司和原因
  - [x] M2-03e 前端 `/campaigns` 列表；導覽列開放「邀請信」 — 2026-11-18

### 寄送防呆
- [x] M2-04 寄送防呆 domain 規則＋測試（F-MAIL-7；拆成下列 a、b） — 2026-11-18
  - [x] M2-04a `domain/send_guard`：排除已退訂、`do_not_contact`、被其他業務鎖定、14 天內寄過、沒有聯絡人的對象。回傳原因代碼，每條規則至少一個 test — 2026-11-18
  - [x] M2-04b 產生草稿時和真正寄出前都要檢查（寄出前再查一次）＋ API 測試 — 2026-11-18

### 預覽佇列
- [x] M2-05 預覽佇列頁（F-MAIL-4；拆成下列 a～c） — 2026-11-18
  - [x] M2-05a 後端： — 2026-11-18
    - `GET /campaigns/{id}/drafts`
    - `PATCH /drafts/{id}`（修改、核准、丟棄）
    - `POST /drafts/{id}/regenerate`
    - 全部核准（要帶確認參數）
    - 丟棄後公司狀態退回 `approved`
  - [x] M2-05b 前端 `/campaigns/:id`（路由依 SPEC 6.2 改成批次頁本身）： — 2026-11-18
    - 左邊清單、右邊預覽，逐封修改
    - 顯示產生進度
    - 只用鍵盤就能逐封核准
  - [x] M2-05c 「全部核准」要再按一次確認；核准後公司狀態改成 `draft_approved` — 2026-11-18

### 寄出
- [x] M2-06 只有核准的草稿可以寄＋測試（F-MAIL-5；拆成下列 a） — 2026-11-18
  - [x] M2-06a 寄送前在 domain 檢查：不是 `approved` 一律回 `DRAFT_NOT_APPROVED`。測試 `test_f_mail_5_*` 要涵蓋每一種非核准狀態 — 2026-11-18
- [x] M2-07 Graph `sendMail`（`MAIL_MODE=sandbox` / `live`）、每日上限、排程（F-MAIL-6；拆成下列 a～e） — 2026-11-18
  - [x] M2-07a `services/mailer` 介面： — 2026-11-18
    - `SandboxMailer` 只寫資料庫和 log（開發、測試用）
    - 測試用的假 Graph
    - 確認 log 不會印出信件全文
  - [x] M2-07b `GraphMailer`： — 2026-11-18
    - 先建立草稿再送出，才拿得到 message id 和 conversation id
    - 失敗時指數退避重試 3 次
  - [x] M2-07c 業務「連結 Outlook」（ADR 0005）： — 2026-11-18
    - `GET/POST/DELETE /me/mail-connection`，用 On-Behalf-Of 換權杖，Fernet 加密存放
    - 新增 `msal` 套件，設定 `ENTRA_CLIENT_SECRET`、`MAIL_TOKEN_KEY`（`.env.example` 同步）；`MAIL_MODE=live` 少了這兩個就啟動失敗
    - 權杖失效時標成 `needs_reconnect`，暫停寄送並提示業務
    - 測試：回應與 log 不含權杖、只能用本人權杖、假的 OBO／Graph
  - [x] M2-07d `POST /campaigns/{id}/send`（可帶 `scheduled_at`）＋ worker `send_scheduled`（寄出成功時開案在 M3-08 接上）： — 2026-11-18
    - 每人每天上限、每分鐘限速，超過的排到隔天
    - 寫入 `email_message` 和 `activity_log`
    - 公司狀態改成 `sent`
  - [x] M2-07e 重試都失敗時，草稿標記 `failed`，在 campaign 頁通知寄件的業務 — 2026-11-18

### 收尾
- [x] M2-08 計算改稿幅度 `edit_ratio`（F-MAIL-8；拆成下列 a） — 2026-11-18
  - [x] M2-08a `domain` 計算函式（0 = 沒改，1 = 全部重寫），核准時寫入，加上測試 — 2026-11-18
- [x] M2-12 KPI 卡「近 7 天已寄出」接上真實資料，在瀏覽器確認 — 2026-11-18
- [x] M2-13 sandbox 走完一輪：10 家 → 產生 → 修改 → 核准 → 寄出，`email_message` 有 10 筆 — 2026-11-18（腳本跑 API＋worker；修掉 contact_id 未填的 bug）
- [x] M2-14 375px / 1280px 瀏覽器檢查；預覽佇列可以只用鍵盤核准 — 2026-11-18
- [ ] M2-15 驗收：真實 Outlook 寄 10 封到測試信箱，確認出現在寄件備份（等 SPEC 11-4 權限核准；只能寄到公司內部的測試信箱）

## M3 案件追蹤與總覽（閉環）

依 2026-11-17 會議調整（ADR 0004）：先做出「寄信 → 人工回填 → 成交」的閉環，AI 寫信移到 M4。
完成條件（SPEC 10）：用 100 筆名單寄出後，模擬一位客戶回覆並回填到成交，總覽頁的回覆率、成交數、待辦提醒都正確。
2026-11-18 已依 CLAUDE.md 第 13 節拆成一個 commit 做得完的大小。建議順序：先做閉環（M3-07～M3-12、M3-04），再做 CSV v1 與名單功能（M3-06、M3-13），最後 M3-14 示範、M3-15 檢查。

- [~] M3-01 prompt `invite_v1`＋`template_ai` / `full_ai` 生成（F-MAIL-2、F-MAIL-3）（取消：移到 M4-06，會議決定先做追蹤閉環）
- [~] M3-02 Graph 收件匣訂閱與回覆比對（F-TRK-1）（取消：不讀業務信箱，改人工回填，見 ADR 0004；自動化改為 M5-03 專用信箱轉寄）
- [~] M3-03 回覆態度分類（F-TRK-2）（取消：移到 M4-07，改成依回填內容分類）
- [x] M3-04 退訂處理：客戶用任何管道要求時，業務手動標記（F-CASE-5、F-TRK-3；拆成下列 a）
  - [x] M3-04a 案件頁「客戶要求退訂」：標記聯絡人退訂、公司改 `do_not_contact`、案件結案（結果 `lost`，備註「退訂」），時間軸留紀錄＋測試 — 2026-11-18（聯絡人退訂也會一併結案）
- [~] M3-05 商機階段與金額（F-TRK-4）（取消：併入 M3-09 案件回填）
- [x] M3-06 CSV 欄位規格 v1（SPEC 8.4） — 2026-11-18
  - [x] M3-06a migration 0009：`company` 加 `country`、`url_status`、`source`；`classification` 加 `fit_stars`、`product_type`、`tags`；匯入批次存漏斗前段數字（單獨 commit） — 2026-11-18
  - [x] M3-06b 匯入器支援新欄位、`invalid` 網址列為「略過」、未知欄位提示；附一份範例 CSV（假資料）給 MLE — 2026-11-18（範例在 `docs/samples/import_v1_sample.csv`；舊版 Excel 沒有來源欄照樣匯入並提示；API 匯入可帶 `funnel`）
  - [x] M3-06c 推薦清單顯示小數星等，新增篩選條件：國別、來源、網址狀態、產品類型、標籤、星等下限（F-REC-1、F-REC-7） — 2026-11-18
- [x] M3-07 migration：`opportunity` 改名擴充為 `sales_case`，新增 `case_update`（拆成下列 a）
  - [x] M3-07a migration 0006（單獨 commit）： — 2026-11-18
    - `opportunity` 沒有資料也沒有程式在用，直接改建成 `sales_case`：編號 `case_no`（C-0001）、公司、聯絡人、負責業務、來源（`email`／`tracking`）、狀態、寄出日、最後回填時間、下次追蹤日、成交金額、結案時間
    - 同一家公司同時只能有一件未結案的案件（部分唯一索引）
    - `case_update`：管道（email／line／wechat／phone／visit／other／system）、聯絡人、結果（replied／negotiating／won／lost／no_response／sent）、備註、下次追蹤日、金額
    - ORM、`schema.sql`、SPEC 8.1 同步
- [x] M3-08 `domain` 案件規則：狀態轉換、回填帶動公司狀態、逾期判斷（7 天、下次追蹤日、14 天）＋單元測試（拆成下列 a）
  - [x] M3-08a `domain/case_rules.py`： — 2026-11-18（待辦條件放在 view，domain 只放天數與「標成無回應」判斷）
    - 案件狀態機（sent／tracking → replied → negotiating → won／lost；無回應 `no_response` 可以再回填）
    - 回填結果對應公司狀態，跳級時依序走過中間狀態（例如 sent 直接回填成交 → replied → meeting → won）
    - 「加入追蹤」的公司是 `approved`，公司狀態機加上 `approved → replied／lost`（SPEC 3.1 同步）
    - 待辦判斷：寄出 7 天沒有回填、超過下次追蹤日、寄出 14 天沒回覆
- [x] M3-09 案件 API：寄出時自動開案（F-CASE-1）、`POST /cases` 加入追蹤（F-REC-9）、`POST /cases/{id}/updates` 回填（F-CASE-2）、列表與詳情（拆成下列 a、b）
  - [x] M3-09a `services/case_service`：worker 寄出成功時開案（已有未結案案件就在時間軸加一筆「寄出」）；`POST /cases` 批次加入追蹤（整批檢查權限與鎖定）＋測試 — 2026-11-18
  - [x] M3-09b `GET /cases`（狀態、負責業務、寄信日、只看逾期；各狀態件數）、`GET /cases/{id}`（時間軸）、`POST /cases/{id}/updates` 回填（帶動公司狀態、寫 `activity_log`）、`GET /cases/export` CSV＋權限測試（業務只看自己的） — 2026-11-18（和 M3-09a 同一個 commit：API 與 service 一起測）
- [x] M3-10 worker 每日催辦（`job` 排程）＋ `GET /reminders`（F-CASE-3；拆成下列 a、b）
  - [x] M3-10a migration 0007（單獨 commit）：view `v_case_reminder`（逾期未回報、該追蹤了、無回應建議拜訪），提醒條件只在 view 定義一次 — 2026-11-18
  - [x] M3-10b worker `case_daily`：每天把寄出 14 天沒回覆的案件標成 `no_response`（時間軸記一筆 system），做完排下一次；worker 啟動時確保有一筆排程；`GET /reminders`＋測試 — 2026-11-18（另外新增 migration 0008 讓 `job.kind` 接受 `case_daily`）
- [x] M3-11 前端 `/cases`：列表、各狀態件數、時間軸、回填表單；可以只用鍵盤回填（F-CASE-4；拆成下列 a、b）
  - [x] M3-11a `/cases` 列表：各狀態件數、篩選（反映在網址）、逾期標記、匯出 CSV；導覽列加「案件」 — 2026-11-18
  - [x] M3-11b `/cases/:id` 詳情：時間軸、回填表單（管道、結果、備註、下次追蹤日、成交金額）、Vitest — 2026-11-18（`/cases/:id` 是同一頁右側詳情，可直接連結）
- [x] M3-12 總覽頁 `/overview`：KPI、名單漏斗、各來源回覆率、待辦提醒（F-DASH-1～4，數字只從 view 來；拆成下列 a、b） — 2026-11-18
  - [x] M3-12a migration 0010（單獨 commit；0008 已用在 job.kind、0009 用在 CSV 欄位）：`v_case_fact`（每件案件一列，含是否回覆、成交、金額、產業、來源、業務、寄出日）；`v_kpi_summary` 的回覆率改用案件（不再讀 `email_event`） — 2026-11-18（另加 `v_company_fact` 給名單漏斗；`v_kpi_summary` 最後面加 `won_total`、`won_amount_twd`）
  - [x] M3-12b `GET /metrics/overview`（日期區間、產業、業務篩選）＋前端 `/overview`：KPI、漏斗、各來源回覆率（少於 10 封標「樣本不足」）、待辦件數可點進清單；導覽列加「總覽」 — 2026-11-18（另加產品類型篩選；業務只看自己的案件）
- [x] M3-13 候選名單欄位自選、匯出 CSV、批次「加入追蹤」（F-REC-8、F-REC-9；拆成下列 a～c） — 2026-11-18
  - [x] M3-13a `GET /companies/export`：依目前篩選匯出 CSV（UTF-8 BOM，Excel 開得了）＋測試 — 2026-11-18（`columns` 指定欄位與順序，沒給用預設 8 欄；最多 20,000 列；不含聯絡人 email）
  - [x] M3-13b 推薦清單欄位自選（最多 10 欄，存在瀏覽器）＋匯出按鈕 — 2026-11-18（公司名稱必選；匯出照畫面上的欄位與篩選）
  - [x] M3-13c 推薦清單批次「加入追蹤」（呼叫 `POST /cases`） — 2026-11-18
- [x] M3-14 示範閉環：100 筆假資料名單 → 寄出（sandbox）→ 模擬一位客戶回覆並回填到成交 → 總覽與待辦正確 — 2026-11-18（API 匯入 100 家 → 審核 → 100 封 sandbox 寄出 → 一件回填回覆→成交 NT$180,000、一件洽談中設今天追蹤；總覽：寄出 100、回覆率 2.0%、成交 1、該追蹤了 1。修掉業務漏斗「已寄信」為 0 的 bug）
- [x] M3-15 375px / 1280px 瀏覽器檢查、鍵盤操作檢查 — 2026-11-18（總覽、推薦清單 375px 沒有橫向捲軸；欄位自選與案件回填可以只用鍵盤完成；修正 MLE 漏斗數字顯示順序）

## M4 AI 寫信、績效與回饋（之後再拆細）

- [ ] M4-01 績效頁：漏斗、各星級成交率、各來源／標籤／模板回覆率、業務排行（F-TRK-5）
- [ ] M4-02 排除原因報表（F-MLE-1）
- [ ] M4-03 回饋資料匯出（F-MLE-2）
- [ ] M4-04 盲標工作台＋「不含模型欄位」測試（F-MLE-3）
- [ ] M4-05 模型品質頁（F-MLE-4）
- [ ] M4-06 prompt `invite_v1`＋`template_ai` / `full_ai` 生成（F-MAIL-2、F-MAIL-3；原 M3-01）。先用地端 LLM（ADR 0006），拆成下列 a～d
  - [ ] M4-06a `LlmClient` 介面＋`LocalLlmClient`（OpenAI 相容 API）＋`FakeLlmClient`；`LLM_PROVIDER` 等設定加進 `.env.example`；JSON 驗證、簡體字檢查、逾時重試＋測試
  - [ ] M4-06b 選地端模型：2～3 個候選模型、同一批 10 家公司，業務盲評品質，記錄速度與硬體需求，結果寫回 ADR 0006
  - [ ] M4-06c prompt `invite_v1`＋`template_ai` / `full_ai` 接進 worker `generate_drafts`；草稿記錄 provider、模型、prompt 版本（migration）
  - [ ] M4-06d `ClaudeClient`（保留切換選項，用假的實作測試；要不要上線看 M4-06b 結果）
- [ ] M4-07 依回填內容判斷回覆態度（F-TRK-2；原 M3-03）
- [ ] M4-08 官網摘要：給 AI 寫信用的公司背景（SPEC 7.4；M4-06 的前置）
  - migration：新增 `company_site_summary` 表（公司、抓取網址、摘要、抓取時間、狀態、錯誤代碼），`job.kind` 加上 `fetch_site`
  - worker `fetch_site`：匯入確認後、或業務修正官網後排進佇列，不在匯入的 request 裡等
  - 只抓首頁和產品／關於我們頁；遵守 robots.txt，設定逾時與大小上限，同網域限速
  - 抓不到或沒有官網就標記失敗，寫信時改用推薦理由，不擋產生草稿
  - 摘要用地端 LLM 產生（ADR 0006）；只留公司產品與產業描述，不存網頁上的人名、email、電話
  - 側欄顯示摘要和抓取時間，業務可以按「重新抓取」
  - 測試：用假的 HTTP 回應，不連真實網站

## M5 延伸（之後再拆細）

- [ ] M5-01 來源管理頁 `/admin/sources`（F-SRC-1）
- [ ] M5-02 產品標籤維護 `/admin/tags`（F-TAG-1）
- [ ] M5-03 專用信箱轉寄、自動比對案件，業務確認後才生效（F-TRK-1）
- [ ] M5-04 給管理者的 BI 儀表板（案件數、成功開案數）

---

## 開發中發現、還沒排進階段的事

- [x] 新增 `.gitattributes` 統一 LF 換行（部署到 Linux 前） — 2026-11-17
- [ ] 前端 bundle 651 kB（超過 500 kB 警告）：dev 模式不需要 MSAL，可改成動態載入或依路由切分
- [ ] 手機版篩選列有 8 個欄位，佔掉一整個螢幕；考慮收合成「篩選」按鈕
- [ ] 原始 Excel 第 44 列缺統編，匯入時會被略過；請 MLE 或業務補上
- [ ] 公司詳情側欄打開時焦點落在「排除…」按鈕，改成落在標題或關閉鈕比較安全
- [ ] 審核結果 CSV 的時間是 UTC ISO 格式，確認 MLE 是否需要台灣時間
- [ ] `RecommendationsPage` 與 `AdminImportsPage` 尚無元件測試（目前靠瀏覽器檢查），M2 前補上（進行中：已完成 RecommendationsPage 的加入追蹤與小數星等測試，AdminImportsPage 還沒有）
- [ ] 寄送時段：`SEND_DAY_START_HOUR`（預設 9 點）之前按寄出會排到當天 9 點；要不要也設下班時間上限，請業務確認
- [ ] 批次全部核准後狀態仍顯示「待審核」（`reviewing`），直到按寄出才變「已排程」；考慮加一個「待寄出」狀態或改顯示文字
- [ ] 建立批次頁的候選公司超過 50 家時沒有搜尋或篩選，M3-13 候選名單改版時一併處理
- [ ] 聯絡人「取消退訂」目前沒有入口（PATCH 不能改 `unsubscribed`）；若客戶主動要求恢復聯絡，需決定由誰、怎麼操作
- [ ] 寄信不會自動認領公司（`owner_id` 留空，只有「認領」或「加入追蹤」才會），寄出後其他業務 14 天後仍可寄；要不要寄出時自動認領，請業務主管決定（M3-14 發現）
- [ ] 欄位自選等受控對話框關閉後，焦點回到頁面最上面而不是原本的按鈕；`Modal` 元件可加上關閉後還原焦點
- [ ] 推薦清單篩選列 M3-06c 後變成 14 個欄位，手機上更長；和上面「收合成篩選按鈕」一起處理
- [ ] 總覽的比例（回覆率、留存率）在 `metrics_service` 依篩選加總後計算，「寄出未滿 10 件不算」的門檻同時寫在 `v_kpi_summary` 和 `metrics_service.MIN_SAMPLE`；若要只定義一次，可改成 SQL 函式
