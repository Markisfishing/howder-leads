# 厚達電子 潛在客戶推薦與邀請信系統 — 規格書 (SPEC)

| 項目 | 內容 |
|---|---|
| 版本 | v0.1（草案） |
| 日期 | 2026-11-17 |
| 主要使用者 | 厚達電子業務部 |
| 相關檔案 | `backend/db/schema.sql`（資料庫）、`frontend/src/styles/design-tokens.css`（視覺規範）、`frontend/prototypes/recommendations.html`（推薦清單頁原型）、`CLAUDE.md`（開發規則） |

---

## 1. 目標與範圍

### 1.1 要解決的問題
業務現在用 Excel 看工具產出的名單，再自己一封一封寫信。這樣有四個問題：
- 不知道該先聯絡誰。
- 不同業務可能寄給同一家公司。
- 寄出去之後沒有紀錄。
- MLE 拿不到「哪些推薦其實是錯的」這種回饋。

### 1.2 系統要做到的事
1. 把模型評分後的名單，以**星級排序**呈現給業務。
2. 讓業務**審核**誰值得合作（通過或排除，排除時要寫原因）。
3. 對通過的名單**批次產生邀請信**（套模板，或模板加上 AI 個人化），業務**預覽、修改、核准**後才寄出。
4. 用公司的 Outlook 帳號寄出，並**追蹤回覆與後續成果**。
5. 把審核結果和成效**回饋給 MLE**，讓 MLE 重新調整模型。

### 1.3 不在這一版的範圍
- 自動找聯絡人 email（先手動輸入，或從官網抓到後由人確認）
- 完整的 CRM 功能（報價單、出貨），只記錄商機的階段和金額
- 行動 App（網頁要支援手機瀏覽，但不另外做 App）

---

## 2. 角色與權限

| 角色 | 可以做的事 |
|---|---|
| 業務 `sales` | 看推薦清單、審核、認領公司、產生和核准自己的郵件、更新自己的商機 |
| 主管 `manager` | 業務能做的全部，再加上看全團隊的績效、重新分派公司 |
| 管理員 / MLE `admin` | 匯入名單、管理模板、管理使用者、看模型品質和回饋報表 |

登入方式：用公司的 Microsoft 帳號登入（Microsoft Entra ID 的 OIDC），**不另外建立帳號密碼**。

---

## 3. 端到端流程

```
[MLE] input → function(評分模型) → CSV ─(匯入)─► [業務 Web]
                    ▲                               ① 推薦清單（星級）
                    │                                   │ check：通過 / 排除(原因)
                    │                                   ▼
                    │                               ② 通過名單 ◄── 業務也可自行加入公司
                    │                                   │ 選模板 + 生成模式
                    │                                   ▼
                    │                               ③ Agent 批次產生草稿
                    │                                   ▼
                    │                               ④ 預覽 / 修改 / 核准
                    │                                   ▼
                    │                               ⑤ 經 Outlook 寄出（排程、限速）
                    │                                   ▼
                    └──── 回饋（排除原因、成效）◄──── ⑥ 追蹤回覆 → 商機 → 成交
```

### 3.1 公司狀態機（`company.status`）

```
imported → pending_review ─┬─► approved → drafted → draft_approved → sent ─┬─► replied → meeting → won
                           │                                              │                       └► lost
                           └─► rejected                                   └─► do_not_contact（退信/退訂）
```

規則：
- 每一次狀態變更都要寫進 `activity_log`，記錄誰在什麼時候從什麼狀態改成什麼狀態。
- `rejected` 一定要附 `reject_reason`（資料庫用 CHECK 強制）。
- `do_not_contact` 是終點，之後任何 campaign 都不能把這家公司選進去。
- 業務按下「認領」之後，這家公司會被鎖定 30 天（`owner_locked_until`），其他業務不能寄信給它。

---

## 4. 功能需求

格式說明：**ID｜需求｜驗收條件**

### 4.1 名單匯入（管理員）
| ID | 需求 | 驗收條件 |
|---|---|---|
| F-IMP-1 | 上傳 CSV / XLSX | 支援 UTF-8 和 Big5 編碼，檔案上限 10 MB |
| F-IMP-2 | 匯入前先預覽 | 顯示「新增 X、更新 Y、錯誤 Z」和每一筆錯誤的原因；要按「確認匯入」才會寫入。畫面匯入時有錯誤的列會略過、其餘照常寫入；API 匯入（F-IMP-5）有任何錯誤就整批拒絕 |
| F-IMP-3 | 用統編去重 | 同一份檔案匯入兩次，`company` 的筆數不會增加 |
| F-IMP-4 | 檢查欄位 | 統編必須是 8 碼數字；產業和優先級必須是維度表裡有的值，否則列入錯誤 |
| F-IMP-5 | API 匯入 | `POST /api/v1/imports/api` 可以收 JSON，之後 MLE 的 function 可以直接寫入，不用再經過 CSV |

### 4.2 推薦清單（業務的首頁）
| ID | 需求 | 驗收條件 |
|---|---|---|
| F-REC-1 | 星級排序列表 | 預設依星級、再依分數由高到低排序；每一列顯示：星級、公司名、產業、使用可能性、推薦理由（一行摘要）、狀態、負責人 |
| F-REC-2 | 篩選 | 可以依產業、星級、狀態、負責人、有沒有官網、是不是競合篩選；篩選條件會反映在網址上，方便分享 |
| F-REC-3 | 批次審核 | 勾選多家公司後可以一次「通過」；「排除」要選原因（單選）加上選填的備註 |
| F-REC-4 | 公司詳情側欄 | 點一列就打開側欄，顯示完整理由、官網、登記產品、聯絡人、往來紀錄；可以在這裡修正官網和產業 |
| F-REC-5 | KPI 卡 | 頁面上方顯示：待審家數、5 星家數、本週已寄、回覆率 |
| F-REC-6 | 手動加入公司 | 輸入統編或公司名稱後加入，系統標記 `added_manually = true` |

### 4.3 寄信工作台
| ID | 需求 | 驗收條件 |
|---|---|---|
| F-MAIL-1 | 建立 campaign | 從「已通過」的名單中勾選對象，再選模板和生成模式 |
| F-MAIL-2 | 三種生成模式 | `template_only`：只代入變數。`template_ai`：模板中的 `{{ai_paragraph}}` 由 AI 撰寫。`full_ai`：整封由 AI 撰寫 |
| F-MAIL-3 | 批次非同步產生 | 50 封草稿 3 分鐘內產生完；畫面顯示進度；單封失敗不影響其他封 |
| F-MAIL-4 | 預覽佇列 | 左邊是清單，右邊是預覽；可以逐封修改、重新生成、刪除、核准，也可以「全部核准」（要再按一次確認） |
| F-MAIL-5 | 只有核准的才寄 | API 拒絕寄送任何不是 `approved` 狀態的草稿 |
| F-MAIL-6 | 寄送 | 透過 Microsoft Graph `sendMail` 從業務本人的信箱寄出；支援排程；每人每天上限 N 封（預設 50 封，可以設定） |
| F-MAIL-7 | 防呆 | 已退訂、`do_not_contact`、被其他業務鎖定、或 14 天內已經寄過的對象，產生草稿時就自動排除，並告訴業務原因 |
| F-MAIL-8 | 記錄改稿幅度 | 核准時計算 `edit_ratio`，也就是業務改了 AI 原稿的比例 |

### 4.4 追蹤與績效
| ID | 需求 | 驗收條件 |
|---|---|---|
| F-TRK-1 | 自動偵測回覆 | 透過 Graph 訂閱收件匣，依 `conversation_id` 比對；收到回覆 5 分鐘內，公司狀態變成 `replied` |
| F-TRK-2 | 判斷回覆的態度 | AI 把回覆分成正向、中性、負向；業務可以手動修正 |
| F-TRK-3 | 退信和退訂 | 退信或退訂後，聯絡人標記 `unsubscribed`，公司改成 `do_not_contact` |
| F-TRK-4 | 商機 | 業務可以更新階段（contacted → meeting → quote → sample → won/lost）和金額 |
| F-TRK-5 | 績效頁 | 顯示漏斗、**各星級的回覆率和成交率**、各模板的回覆率、業務排行 |

### 4.5 MLE 回饋與模型品質（管理員）
| ID | 需求 | 驗收條件 |
|---|---|---|
| F-MLE-1 | 排除原因報表 | 依 model run 統計排除原因的分布 |
| F-MLE-2 | 匯出訓練資料 | `GET /api/v1/feedback/export?run_id=` 下載 CSV，內含模型預測、業務決策、修正值和最後成果 |
| F-MLE-3 | 盲標工作台 | 只顯示公司名、登記產品和官網；**API 回應不包含任何模型欄位** |
| F-MLE-4 | 模型品質 | 各 run 的產業準確率、混淆矩陣、潛在客戶判斷的 Precision 和 Recall（以 gold label 為準） |

---

## 5. 系統架構

```
            ┌───────────────────── 公司內網 / 雲端 VM（Docker Compose）─────────────────────┐
 瀏覽器 ───►│ Nginx (HTTPS) ─┬─► Frontend：靜態檔案 (React build)                            │
            │                └─► Backend API：FastAPI (uvicorn)  ──► PostgreSQL 16           │
            │                          └─► Worker（從 PostgreSQL 佇列領工作）                 │
            │                                ├─ 產生草稿 ──► Claude API                       │
            │                                ├─ 寄信 / 讀回覆 ──► Microsoft Graph             │
            │                                └─ 匯入解析、排程寄送                            │
            └──────────────────────────────────────────────────────────────────────────────────┘
 MLE function ──(CSV 或 POST /api/v1/imports，帶 API key)──► Backend
```

選這套技術的理由：
- **Python 後端：** MLE 的 function 是 Python，匯入解析也要用 pandas，用同一種語言可以共用程式碼。
- **非同步 Worker：** 產生 50 封信、寄信都很花時間，放在背景執行，網頁不會卡住。佇列直接放在 PostgreSQL（`SKIP LOCKED`），不另外架 Redis（ADR 0003）。
- **Docker Compose：** 部署在公司內網一台主機上就能跑，不需要 Kubernetes。

---

## 6. 前端

### 6.1 技術
| 項目 | 選擇 | 理由 |
|---|---|---|
| 框架 | React 19 + TypeScript + Vite | 頁面互動多（批次勾選、側欄、預覽佇列），需要元件化 |
| 路由 | React Router | |
| 資料抓取 | TanStack Query | 處理快取、重試，也能輪詢草稿產生的進度 |
| 樣式 | **CSS Modules + `frontend/src/styles/design-tokens.css` 變數；元件行為用 Radix UI Primitives（無樣式）** | 互動元件（對話框、選單、側欄）需要鍵盤和焦點管理，Radix 只提供行為和 ARIA，外觀完全用 tokens；不使用帶樣式的框架和外部字型 |
| 表格 | TanStack Table（只用邏輯，不帶樣式） | 支援排序、勾選、虛擬捲動 |
| 郵件編輯 | 只開放少數格式（粗體、連結、段落）的編輯器 | 避免業務貼上奇怪格式，讓信件在各家信箱顯示一致 |
| 圖表 | 自己用 SVG 畫 | 圖表只有長條圖和漏斗，不需要引入大型圖表套件 |

### 6.2 路由與頁面
| 路由 | 頁面 | 角色 |
|---|---|---|
| `/` | 推薦清單（含 KPI 卡、篩選、詳情側欄） | 全部 |
| `/companies/:id` | 公司詳情（可以直接連結） | 全部 |
| `/campaigns` | 我的 campaign 列表 | 全部 |
| `/campaigns/new` | 建立 campaign：選對象 → 選模板和生成模式 | 全部 |
| `/campaigns/:id/review` | 預覽佇列（產生進度、逐封審核） | 全部 |
| `/performance` | 績效：漏斗、各星級成交率、各模板回覆率 | 全部（主管可看全團隊） |
| `/admin/imports` | 匯入與預覽 | admin |
| `/admin/templates` | 模板管理 | admin |
| `/admin/model` | 模型品質、排除原因、匯出回饋資料 | admin |
| `/admin/labeling` | 盲標工作台 | admin |

### 6.3 版面與視覺
- 版面：左側導覽列（寬螢幕）或上方選單（手機），右側是內容區。主要使用情境是 1280px 以上的桌機，但 375px 寬也要能看清單和預覽信件。
- 斷點：768px 和 1024px。
- 配色：來自厚達品牌色（logo 的紅、HOWDER 字樣的橘、炭灰），**降低彩度後只用在強調處**。大面積用暖灰白底，避免整片紅色。詳細色值見 `frontend/src/styles/design-tokens.css`。
- 星級用品牌橘，狀態標籤用低彩度的底色加上深色字，對比都要達到 WCAG AA 標準（4.5:1）。
- 主色是磚紅 `--color-accent`，用在主要按鈕、連結和選取狀態。「錯誤」和「排除」用更暗、偏棕的 `--color-danger`，而且一律附文字，避免和主色按鈕搞混。

---

## 7. 後端

### 7.1 技術
FastAPI、Pydantic v2、SQLAlchemy 2 和 Alembic（資料庫 migration）、PostgreSQL 佇列（背景工作，ADR 0003）、pandas（匯入解析）、`msal`（Microsoft 登入和 Graph 權杖）、Anthropic SDK（產生郵件）。

### 7.2 模組切分
```
backend/app/
  api/v1/        路由：auth, companies, reviews, imports, campaigns, drafts, messages, metrics, feedback
  domain/        商業規則：狀態機轉換、寄送防呆、鎖定規則（不依賴 FastAPI，方便單元測試）
  services/
    importer.py   解析 CSV/XLSX → 驗證 → 產生預覽差異 → 確認後寫入
    generator.py  依生成模式組 prompt → 呼叫 Claude → 回填草稿
    mailer.py     Graph 寄信、訂閱收件匣、處理 webhook
    metrics.py    讀取 SQL view，不在 Python 裡重算 KPI
  workers/       背景工作（PostgreSQL 佇列）：generate_drafts, send_scheduled, sync_replies
  models/        SQLAlchemy ORM（和 backend/db/schema.sql 一致）
```

### 7.3 API（REST，前綴 `/api/v1`）
| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/me` | 目前登入的使用者和角色 |
| GET | `/companies?stars=&industry=&status=&owner=&q=&sort=&page=` | 推薦清單（讀 `v_recommendation`） |
| GET | `/companies/{id}` | 詳情，包含分類、聯絡人、活動紀錄 |
| PATCH | `/companies/{id}` | 修正官網、產業、加備註 |
| POST | `/companies/{id}/claim`、`/release` | 認領（鎖定 30 天）／釋出 |
| POST | `/companies/{id}/assign` | 主管重新分派 |
| POST | `/companies` | 手動加入公司 |
| POST | `/reviews` | 批次審核 `{company_ids[], decision, reject_reason?, note?, corrected_industry_id?}`；整批成功才寫入 |
| POST | `/contacts` / PATCH `/contacts/{id}` | 管理聯絡人 |
| POST | `/imports` | 管理員上傳 CSV / XLSX → 回傳預覽（`status = previewed`） |
| POST | `/imports/api?commit=` | MLE function 用 JSON 匯入（`X-API-Key`）；`commit=true` 直接寫入，有錯誤就整批拒絕 |
| GET | `/imports`、`/imports/{id}` | 匯入紀錄與預覽內容 |
| POST | `/imports/{id}/cancel` | 取消預覽中的批次 |
| POST | `/imports/{id}/commit` | 確認匯入 |
| GET/POST/PATCH | `/templates` | 模板管理（admin） |
| POST | `/campaigns` | 建立 campaign，並開始產生草稿（回傳 `job_id`） |
| GET | `/campaigns/{id}/drafts?status=` | 預覽佇列 |
| PATCH | `/drafts/{id}` | 修改內容、核准或丟棄 |
| POST | `/drafts/{id}/regenerate` | 重新生成這一封 |
| POST | `/campaigns/{id}/send` | 寄出全部已核准的草稿（可帶 `scheduled_at`） |
| POST | `/webhooks/graph` | Graph 推送通知（回覆、退信） |
| GET | `/metrics/kpis` | 推薦清單頁的 KPI 卡（讀 `v_kpi_summary`） |
| GET | `/metrics/{funnel\|win-rate\|templates\|reps}` | 績效資料（M4） |
| GET | `/dimensions` | 下拉選單用：產業、優先級、排除原因、狀態、業務名單 |
| GET | `/admin/reviews/export` | 審核紀錄 CSV（含當時模型判斷），給 MLE 用 |
| GET | `/feedback/export?run_id=` | 匯出給 MLE 的資料 |
| GET | `/labeling/next` / POST `/labeling` | 盲標 |

統一的錯誤格式：`{ "error": { "code": "DRAFT_NOT_APPROVED", "message": "…" } }`

### 7.4 AI 郵件產生
- 模型：Claude（`claude-sonnet-5-5`），一家公司呼叫一次，並發數限制為 5。
- 輸入：模板、公司名稱、產業、客戶屬性、判斷理由、官網摘要（匯入時預先爬取並快取），再加上厚達的產品介紹（固定的 system prompt，使用 prompt caching）。
- 輸出：要求回傳 JSON `{subject, ai_paragraph | body_html}`，並驗證長度和必要欄位。
- 限制：不得捏造客戶實績、價格或認證；內容只能根據提供的資料撰寫。
- 原稿存在 `ai_original`，業務修改後的版本存在 `body_html`。

### 7.5 寄信（Microsoft Graph）
- 權限：每位業務各自授權 `Mail.Send` 和 `Mail.Read`（delegated 委派權限），信件從本人的信箱寄出，也會留在本人的寄件備份。
- 不直接使用 SMTP：Exchange Online 正在淘汰 SMTP 基本驗證，而且 SMTP 無法讀取回覆。
- 限速：每位寄件人每分鐘最多 N 封，每天最多 50 封，超過的自動排到隔天。
- 每封信的結尾都要有退訂說明。

---

## 8. 資料庫

PostgreSQL 16，完整的 DDL 在 [`backend/db/schema.sql`](../backend/db/schema.sql)。

### 8.1 資料表一覽
| 分組 | 資料表 | 用途 |
|---|---|---|
| 使用者 | `app_user` | 業務、主管、管理員 |
| 維度 | `dim_industry`、`dim_priority` | 18 類產業；A–D 優先級和星級的對照（取代 Excel 裡混在資料欄的圖例） |
| 名單 | `import_batch`、`company` | 匯入批次（預覽時把解析好的資料暫存在 `payload`，確認後才寫入）；公司主檔（統編唯一）、目前狀態、負責業務、業務修正的產業 `industry_override_id` |
| 模型 | `model_run`、`classification` | 每次模型 run 都保留一份分類結果，`is_current` 標示目前生效的那一份 |
| 回饋 | `review`、`gold_label` | 業務審核（排除一定要有原因）；盲標的標準答案 |
| 聯絡 | `contact` | 聯絡人和退訂狀態 |
| 郵件 | `email_template`、`campaign`、`email_draft`、`email_message`、`email_event` | 模板 → 批次 → 草稿（含 AI 原稿）→ 實際寄出 → 事件 |
| 成果 | `opportunity`、`activity_log` | 商機階段和金額；所有變更的稽核紀錄 |
| 指標 | `v_recommendation`、`v_kpi_summary`、`v_funnel`、`v_win_rate_by_priority`、`v_reject_reasons` | **KPI 只在這些 view 定義一次** |

### 8.2 ER 關係（簡化）
```
app_user 1─* company(owner) 1─* classification *─1 model_run
company 1─* review          company 1─1 gold_label
company 1─* contact 1─* email_draft *─1 campaign *─1 email_template
email_draft 1─1 email_message 1─* email_event
company 1─* opportunity     company 1─* activity_log
```

### 8.3 從現有 Excel 轉換時的清理規則
| 原始欄位 | 轉換到 | 處理方式 |
|---|---|---|
| 統編 | `company.tax_id` | 左邊補 0 補到 8 碼 |
| 官網(工具找到的) | `company.website_url` | 空值保留 NULL，`website_verified = false` |
| 端子台使用可能性 = 明確但競合 | `likelihood = 高`、`is_competitor = true` | 把一欄拆成兩欄 |
| 優先級 A–D | `classification.priority` | 星級由 `dim_priority` 對照產生 |
| 建議動作（7 種值） | 不匯入 | 改由 `dim_priority.suggested_action` 推導 |
| 分類 / 家數 / Unnamed: 9 | 不匯入 | 這些是圖例或空欄，內容整理進 `dim_priority` |

---

## 9. 非功能需求

| 類別 | 要求 |
|---|---|
| 效能 | 推薦清單 5,000 筆時，第一頁 < 1 秒；篩選 < 500 ms |
| 安全 | 全站 HTTPS；用 SSO 登入；API 每次都檢查角色；Graph 權杖加密後存放；匯入 API 用 API key |
| 個資 | 聯絡人要記錄來源；提供刪除功能（連帶刪除郵件內容）；退訂必須生效 |
| 稽核 | 狀態變更、寄信、匯入都寫進 `activity_log`，保留 3 年 |
| 可用性 | 寄信失敗會自動重試 3 次（指數退避）；重試都失敗就標記 `failed`，並通知寄件的業務 |
| 備份 | PostgreSQL 每天備份，保留 30 天 |
| 無障礙 | 文字對比 ≥ 4.5:1；可以只用鍵盤完成審核和核准 |

---

## 10. 開發階段

| 階段 | 內容 | 完成條件 |
|---|---|---|
| **M1 MVP** | SSO、匯入（CSV + 預覽）、推薦清單、審核、詳情側欄 | 業務能用 50 家測試名單完成審核，排除原因可以匯出 |
| **M2 寄信** | 模板、`template_only` 生成、預覽佇列、Graph 寄送、防呆、限速 | 一位業務從核准到寄出 10 封信，全部出現在他的 Outlook 寄件備份 |
| **M3 AI 與追蹤** | `template_ai` / `full_ai`、回覆偵測、回覆態度分類、商機 | 回覆可以自動改變公司狀態 |
| **M4 績效與回饋** | 績效頁、模型品質頁、盲標工作台、回饋匯出 | MLE 能拿回饋資料重新訓練，並在模型品質頁比較兩個 run |

---

## 11. 待確認事項

1. 優先級定義：Excel 圖例的順序和資料不完全一致。依 50 筆資料交叉比對，暫定 **A = 使用可能性高**、**B = 中、可開發**、**C = 中但需求不明確，或屬於策略／競合對象**、**D = 低（材料或純零件）**。唯一一筆「明確但競合」被評為 B，和「C 含競合」的說法互相矛盾，請業務主管確認競合對象應該歸在哪一級。
2. 每人每日寄送上限和鎖定天數（目前暫定 50 封、30 天）。
3. 部署位置：公司內網主機或雲端，會影響 Graph webhook 能不能從外部連進來。
4. Microsoft 365 的租用戶管理員能不能核准這個應用程式的 `Mail.Send` / `Mail.Read` 權限。
5. 郵件模板的初版內容和法律聲明（退訂說明）由誰提供。
