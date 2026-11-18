# 厚達電子 潛在客戶推薦與邀請信系統 — 規格書 (SPEC)

| 項目 | 內容 |
|---|---|
| 版本 | v0.2（依 2026-11-17 會議調整：人工回填、案件追蹤、CSV 欄位規格） |
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
- 不知道哪一批名單品質比較好、業務最常因為什麼原因排除。

### 1.2 系統要做到的事
1. 把模型評分後的名單，以**星級排序**呈現給業務。
2. 讓業務**審核**誰值得合作（通過或排除，排除時要寫原因）。
3. 對通過的名單**批次產生邀請信**（套模板，或模板加上 AI 個人化），業務**預覽、修改、核准**後才寄出。
4. 用業務本人的 Outlook 帳號寄出；**每封開發信開成一個案件**，業務人工回填客戶回覆與結果，系統**逾期催辦**，證明名單真的帶來回覆與成交。
5. 用審核結果和成效**評估各批名單的品質**（排除原因、回覆率、成交率）。MLE 只負責產生名單 CSV，之後的作業都在本系統完成，結果**不回傳給 MLE**（2026-11-18 決定）。

### 1.3 不在這一版的範圍
- 自動找聯絡人 email（先手動輸入，或從官網抓到後由人確認）
- 完整的 CRM 功能（報價單、出貨），只記錄商機的階段和金額
- 行動 App（網頁要支援手機瀏覽，但不另外做 App）
- 讀取業務個人信箱自動判斷回覆（業務信箱含大量敏感資訊，屬資料治理問題；第一版人工回填，見 ADR 0004）
- 對外開放：平台只給公司內部使用

---

## 2. 角色與權限

| 角色 | 可以做的事 |
|---|---|
| 業務 `sales` | 看推薦清單、審核、認領公司、產生和核准自己的郵件、更新自己的商機 |
| 主管 `manager` | 業務能做的全部，再加上看全團隊的績效、重新分派公司 |
| 管理員 `admin` | 匯入名單（MLE 產生的 CSV）、管理模板、管理使用者、看名單品質報表 |

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
                    └──── 回饋（排除原因、成效）◄──── ⑥ 案件：人工回填 → 逾期催辦 → 成交
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
- `sent` 之後的狀態（`replied`、`meeting`、`won`、`lost`）由案件回填帶動（4.4），業務不直接改公司狀態。
- 「加入追蹤」（F-REC-9）的公司沒有寄信，停在 `approved`；回填時可以直接 `approved → replied` 或 `approved → lost`。
- 回填跳級時（例如已寄出直接回填成交），公司依序走過中間狀態（`sent → replied → meeting → won`），每一步都寫 `activity_log`；案件狀態對應：已回覆 → `replied`、洽談中 → `meeting`、成交 → `won`、失敗 → `lost`，無回應不改公司狀態。

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
| F-REC-1 | 星級排序列表 | 預設依適合度星等（`fit_stars`，MLE 提供，可到小數一位，例如 4.5）、再依分數由高到低排序；CSV 沒給星等時，由優先級對照（`dim_priority`）。每一列顯示：星級與數字、公司名、產業、使用可能性、推薦理由（一行摘要）、狀態、負責人 |
| F-REC-2 | 篩選 | 可以依產業、星級、狀態、負責人、有沒有官網、是不是競合篩選；篩選條件會反映在網址上，方便分享 |
| F-REC-3 | 批次審核 | 勾選多家公司後可以一次「通過」；「排除」要選原因（單選）加上選填的備註 |
| F-REC-4 | 公司詳情側欄 | 點一列就打開側欄，顯示完整理由、官網、登記產品、聯絡人、往來紀錄；可以在這裡修正官網和產業 |
| F-REC-5 | KPI 卡 | 頁面上方顯示：待審家數、5 星家數、本週已寄、回覆率 |
| F-REC-6 | 手動加入公司 | 輸入統編或公司名稱後加入，系統標記 `added_manually = true` |
| F-REC-7 | 多維度篩選（CSV v1 欄位） | 可再依國別、資料來源、網址狀態、產品類型、命中標籤、星等下限篩選；條件同樣反映在網址上 |
| F-REC-8 | 欄位自選與匯出 | 業務可以選要顯示哪些欄位（最多 10 欄，記在自己的瀏覽器）；可以把目前篩選結果匯出成 CSV |
| F-REC-9 | 批次「加入追蹤」 | 勾選的公司不寄信也能直接開案（例如先打電話、拜訪），之後同樣在案件頁回填 |

### 4.3 寄信工作台
| ID | 需求 | 驗收條件 |
|---|---|---|
| F-MAIL-1 | 建立 campaign | 從「已通過」的名單中勾選對象，再選模板和生成模式 |
| F-MAIL-2 | 三種生成模式 | `template_only`：只代入變數。`template_ai`：模板中的 `{{ai_paragraph}}` 由 AI 撰寫。`full_ai`：整封由 AI 撰寫 |
| F-MAIL-3 | 批次非同步產生 | 50 封草稿 3 分鐘內產生完；畫面顯示進度；單封失敗不影響其他封 |
| F-MAIL-4 | 預覽佇列 | 左邊是清單，右邊是預覽；可以逐封修改、重新生成、刪除、核准，也可以「全部核准」（要再按一次確認）。草稿全部處理完（沒有待審核的）時，批次狀態變成「待寄出」（`ready`），按寄出後才是「已排程」 |
| F-MAIL-5 | 只有核准的才寄 | API 拒絕寄送任何不是 `approved` 狀態的草稿 |
| F-MAIL-6 | 寄送 | 透過 Microsoft Graph `sendMail` 從業務本人的信箱寄出；支援排程；每人每天上限 N 封（預設 50 封，可以設定）。只在台灣時間 `SEND_DAY_START_HOUR`（預設 9 點）到 `SEND_DAY_END_HOUR`（預設 18 點）之間寄；超過下班時間的排到隔天開始時間 |
| F-MAIL-7 | 防呆 | 已退訂、`do_not_contact`、被其他業務鎖定、或 14 天內已經寄過的對象，產生草稿時就自動排除，並告訴業務原因 |
| F-MAIL-8 | 記錄改稿幅度 | 核准時計算 `edit_ratio`，也就是業務改了 AI 原稿的比例 |

### 4.4 案件追蹤與催辦（第一版人工回填，ADR 0004）
每封寄出的開發信自動開一個**案件**（`sales_case`，編號 `C-0001`）。客戶不論用 Email、LINE、微信或電話回覆，都由業務在案件上**人工回填**；系統不讀業務信箱。

| ID | 需求 | 驗收條件 |
|---|---|---|
| F-CASE-1 | 自動開案 | 草稿寄出成功時建立案件（狀態「已寄出」），連到那封信、公司、聯絡人、負責業務；F-REC-9「加入追蹤」也會開案（沒有信件） |
| F-CASE-2 | 人工回填 | 回填一筆紀錄：管道（email／line／wechat／phone／visit／other）、聯絡人、結果（已回覆／洽談中／成交／失敗／無回應）、備註、下次追蹤日、成交金額（成交時選填）。每筆都留在案件時間軸，並帶動公司狀態（`replied`／`meeting`／`won`／`lost`） |
| F-CASE-3 | 逾期催辦 | 每天自動檢查：寄出 7 天沒有任何回填 →「逾期未回報」；超過「下次追蹤日」→「該追蹤了」；寄出 14 天沒回覆 → 標記「無回應」並建議電話或拜訪。提醒出現在業務的待辦清單，直到回填或結案 |
| F-CASE-4 | 案件列表 | 依狀態、負責業務、寄信日、只看逾期篩選；上方顯示各狀態件數；右側是時間軸和回填表單；可以只用鍵盤完成回填；可匯出 CSV |
| F-CASE-5 | 退訂 | 客戶用任何管道表示不要再聯絡時，業務在案件或聯絡人上標記，**只有該聯絡人**改成 `unsubscribed`。公司所有聯絡人都退訂，或客戶明講整家公司都不要聯絡（標記時勾選「整家公司不再聯絡」）時，公司才改成 `do_not_contact`、案件結案為失敗。取消退訂只限主管／管理員，必填原因並寫 `activity_log`（2026-11-18 決定） |

| ID | 需求 | 驗收條件 |
|---|---|---|
| F-TRK-1 | 自動偵測回覆（延伸） | **不讀業務個人信箱。**改用講評者建議的做法：業務把回信轉寄到一個專用信箱，系統從專用信箱比對原始案件與客戶，產生「待確認的回填」，業務確認後才生效。依公司信箱類型評估後再做 |
| F-TRK-2 | 判斷回覆的態度（延伸） | AI 依回填的回覆內容分成正向、中性、負向；業務可以手動修正 |
| F-TRK-3 | 退信 | 寄信時 Graph 回報失敗的對象標記為退信；信箱裡的退信通知要讀信箱，併入 F-TRK-1 再處理 |
| F-TRK-4 | 商機 | 併入案件（F-CASE-2 的結果與金額），不另外維護 `opportunity` |
| F-TRK-5 | 績效頁 | 顯示漏斗、**各星級的回覆率和成交率**、**各資料來源與各產品標籤的回覆率**、各模板的回覆率、業務排行 |

### 4.5 名單品質（管理員、主管）
MLE 只負責產生名單 CSV，結果不回傳給 MLE；原本的 F-MLE-2 匯出訓練資料、F-MLE-3 盲標工作台、F-MLE-4 模型品質在 2026-11-18 取消。

| ID | 需求 | 驗收條件 |
|---|---|---|
| F-MLE-1 | 排除原因報表 | 依匯入批次（model run）統計排除原因的分布，讓主管判斷哪一批名單品質比較差 |

### 4.6 總覽（業務與主管的第一眼）
| ID | 需求 | 驗收條件 |
|---|---|---|
| F-DASH-1 | KPI | 名單公司數、高優先名單數、已寄開發信、回覆率（回覆／寄出）、成交數；可依日期區間、產業、產品類型、業務篩選 |
| F-DASH-2 | 名單漏斗 | 名單 → 審核通過 → 已寄信 → 回覆 → 成交，顯示每一段的留存率。前段「資料庫 3.9 萬 → 產業 → 網址 → 產品 → 高優先」的數字由 MLE 在匯入時一併提供 |
| F-DASH-3 | 各來源回覆率 | 回覆數／寄信數，依資料來源排序；寄信少於 10 封的來源標示「樣本不足」 |
| F-DASH-4 | 待辦提醒 | 逾期未回報、該追蹤了、新名單待審核、無回應建議拜訪，各顯示件數並可點進對應清單 |

### 4.7 來源與產品標籤維護（延伸，主要在 MLE 端）
| ID | 需求 | 驗收條件 |
|---|---|---|
| F-SRC-1 | 來源管理 | 列出資料來源網站（目前約 5 個，之後 10 個以上），可新增、停用，看各來源的撈取筆數與回覆率；可以只部署某個日期區間新增的公司 |
| F-TAG-1 | 產品標籤 | 維護產品標籤（如 AI 伺服器、自動化、電箱）和各標籤的命中數、回覆率；標籤內容由厚達說明產品「用在哪裡」後提供 |

---

## 5. 系統架構

```
            ┌───────────────────── 公司內網 / 雲端 VM（Docker Compose）─────────────────────┐
 瀏覽器 ───►│ Nginx (HTTPS) ─┬─► Frontend：靜態檔案 (React build)                            │
            │                └─► Backend API：FastAPI (uvicorn)  ──► PostgreSQL 16           │
            │                          └─► Worker（從 PostgreSQL 佇列領工作）                 │
            │                                ├─ 產生草稿 ──► 地端 LLM                       │
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
| `/campaigns/:id` | 預覽佇列（產生進度、逐封審核、寄出） | 全部 |
| `/overview` | 總覽：KPI、名單漏斗、各來源回覆率、待辦提醒 | 全部（主管可看全團隊） |
| `/cases` | 案件追蹤：案件列表、時間軸、人工回填 | 全部（業務看自己的，主管看全部） |
| `/cases/:id` | 案件詳情（可以直接連結） | 全部 |
| `/performance` | 績效：漏斗、各星級成交率、各來源／標籤／模板回覆率 | 全部（主管可看全團隊） |
| `/admin/imports` | 匯入與預覽 | admin |
| `/admin/templates` | 模板管理 | admin |
| `/admin/model` | 名單品質：各匯入批次的排除原因 | admin、主管 |
| `/admin/sources`、`/admin/tags` | 來源管理、產品標籤（延伸） | admin |

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
  api/v1/        路由：auth, companies, reviews, imports, campaigns, drafts, messages, metrics
  domain/        商業規則：狀態機轉換、寄送防呆、鎖定規則（不依賴 FastAPI，方便單元測試）
  services/
    importer.py   解析 CSV/XLSX → 驗證 → 產生預覽差異 → 確認後寫入
    generator.py  依生成模式組 prompt → 呼叫 LLM（地端／Claude）→ 回填草稿
    mailer.py     Graph 寄信、訂閱收件匣、處理 webhook
    metrics.py    讀取 SQL view，不在 Python 裡重算 KPI
  workers/       背景工作（PostgreSQL 佇列）：generate_drafts, send_scheduled, sync_replies
  models/        SQLAlchemy ORM（和 backend/db/schema.sql 一致）
```

### 7.3 API（REST，前綴 `/api/v1`）
| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/me` | 目前登入的使用者和角色 |
| GET | `/companies?stars=&industry=&status=&owner=&q=&country=&source=&url_status=&product_type=&tag=&min_stars=&sort=&page=` | 推薦清單（讀 `v_recommendation`；`source=none` 是未標示來源；`/dimensions` 回傳名單裡出現過的國別、來源、標籤給下拉選單） |
| GET | `/companies/{id}` | 詳情，包含分類、聯絡人、活動紀錄 |
| PATCH | `/companies/{id}` | 修正官網、產業、加備註 |
| POST | `/companies/{id}/claim`、`/release` | 認領（鎖定 30 天）／釋出 |
| POST | `/companies/{id}/assign` | 主管重新分派 |
| POST | `/companies` | 手動加入公司 |
| POST | `/reviews` | 批次審核 `{company_ids[], decision, reject_reason?, note?, corrected_industry_id?}`；整批成功才寫入 |
| POST | `/contacts` / PATCH `/contacts/{id}` | 管理聯絡人（來源必填、email 格式檢查、同公司不重複） |
| POST | `/contacts/{id}/unsubscribe` | 標記退訂（F-CASE-5）；帶 `whole_company: true` 或公司已沒有其他可聯絡的人時，公司才改成 `do_not_contact` |
| POST | `/contacts/{id}/resubscribe` | 取消退訂（主管／管理員，body 帶 `reason`），寫 `activity_log` |
| DELETE | `/contacts/{id}` | 個資刪除（主管／管理員，body 帶 `reason`）：連帶刪除草稿與寄出信件，寫 `activity_log` |
| POST | `/imports` | 管理員上傳 CSV / XLSX → 回傳預覽（`status = previewed`） |
| POST | `/imports/api?commit=` | MLE function 用 JSON 匯入（`X-API-Key`）；`commit=true` 直接寫入，有錯誤就整批拒絕 |
| GET | `/imports`、`/imports/{id}` | 匯入紀錄與預覽內容 |
| POST | `/imports/{id}/cancel` | 取消預覽中的批次 |
| POST | `/imports/{id}/commit` | 確認匯入 |
| GET | `/templates`、`/templates/{id}`、`/templates/variables` | 使用中的模板與變數白名單（全部角色可讀） |
| POST/PUT | `/templates`、`/templates/{id}` | 新增模板；修改會新增一個版本（admin） |
| POST | `/templates/{id}/archive`、`/templates/preview` | 停用模板、用假資料預覽（admin） |
| GET | `/templates/{id}/versions` | 同一份模板的所有版本（admin） |
| GET | `/campaigns`、`/campaigns/{id}` | 我的批次（主管看全部），含各狀態草稿數 |
| GET | `/campaigns/candidates` | 可以選進批次的「已通過」公司、聯絡人、不能寄的原因；沿用推薦清單的篩選參數（`q` 公司名稱／統編、`industry_id`、`stars`、`min_stars`…），只縮小範圍（M3-16） |
| POST | `/campaigns` | 建立 campaign，並開始產生草稿（回傳 `job_id` 與被防呆排除的公司） |
| GET | `/campaigns/{id}/drafts` | 預覽佇列 |
| PATCH | `/drafts/{id}` | 修改主旨、內文（只有待審核或失敗的草稿） |
| POST | `/drafts/{id}/approve`、`/unapprove`、`/discard` | 核准（計算 `edit_ratio`）、取消核准、丟棄 |
| POST | `/drafts/{id}/regenerate` | 重新生成這一封（回傳 `job_id`） |
| POST | `/campaigns/{id}/approve-all` | 全部核准，body 要帶 `confirm: true` |
| POST | `/campaigns/{id}/send` | 寄出全部已核准的草稿（可帶 `scheduled_at`；只有批次的負責業務本人可以寄） |
| GET/POST/DELETE | `/me/mail-connection` | 查看、連結、中斷自己的 Outlook 寄信權限（只回傳狀態，不回傳權杖） |
| GET | `/cases?status=&owner=&sent_from=&sent_to=&overdue=` | 案件列表與各狀態件數（業務只看自己的）；`/cases/export` 同條件匯出 CSV（不含 email） |
| GET | `/cases/{id}` | 案件詳情與時間軸 |
| POST | `/cases` | 批次「加入追蹤」`{company_ids[]}`（只限已通過的公司，整批檢查；沒人負責時順便認領） |
| POST | `/cases/{id}/updates` | 人工回填一筆紀錄 |
| POST | `/cases/{id}/unsubscribe` | 客戶要求退訂：聯絡人退訂；整家公司不要聯絡（`whole_company`）或已沒有其他聯絡人時，公司改 `do_not_contact`、案件結案為失敗（F-CASE-5） |
| GET | `/reminders` | 目前使用者的待辦提醒件數（讀 `v_case_reminder`）＋新名單待審核 |
| GET | `/metrics/overview?from=&to=&industry=&product_type=&owner=` | 總覽：KPI、漏斗（含 MLE 附的前段數字）、各來源回覆率、待辦件數（讀 `v_case_fact`、`v_company_fact`）。業務只看自己的案件，`owner` 只有主管能指定；名單數是共用名單池；日期以寄出日（台灣時間）計算 |
| GET | `/companies/export?…&columns=` | 依目前篩選條件匯出 CSV（UTF-8 BOM）；`columns` 指定欄位與順序（和畫面的欄位自選同一組 key），沒給用預設欄位；不含聯絡人 email |
| GET | `/metrics/kpis` | 推薦清單頁的 KPI 卡（讀 `v_kpi_summary`） |
| GET | `/metrics/{funnel\|win-rate\|templates\|reps}` | 績效資料（M4） |
| GET | `/dimensions` | 下拉選單用：產業、優先級、排除原因、狀態、業務名單 |
| GET | `/admin/reviews/export` | 審核紀錄 CSV（含當時模型判斷），內部備查用 |

統一的錯誤格式：`{ "error": { "code": "DRAFT_NOT_APPROVED", "message": "…" } }`

### 7.4 AI 郵件產生
- 模型：**先用地端 LLM**（OpenAI 相容 API，例如 Ollama），用 `LLM_PROVIDER` 可切換成 Claude（`claude-sonnet-5-5`）；一家公司呼叫一次，並發數可設定（ADR 0006）。用哪個地端模型，由 M4-06b 比較後決定。
- 輸入：模板、公司名稱、產業、客戶屬性、判斷理由、官網摘要（匯入確認後由 worker 抓取並快取在 `company_site_summary`，抓不到時改用推薦理由；M4-08），再加上厚達的產品介紹（固定的 system prompt；用 Claude 時開 prompt caching）。
- 輸出：要求回傳 JSON `{subject, ai_paragraph | body_html}`，並驗證長度和必要欄位。
- 限制：不得捏造客戶實績、價格或認證；內容只能根據提供的資料撰寫。
- 原稿存在 `ai_original`，業務修改後的版本存在 `body_html`；同時記錄產生的 provider、模型與 prompt 版本。
- 繁中檢查：回傳內容出現簡體字就算失敗並重試一次。

### 7.5 寄信（Microsoft Graph）
- 權限：每位業務各自授權 **`Mail.Send`**（delegated 委派權限），信件從本人的信箱寄出，也會留在本人的寄件備份。**不申請 `Mail.Read`**，系統不讀業務信箱（ADR 0004）。
- 權杖：業務按「連結 Outlook」時，後端用 On-Behalf-Of 換到 Graph 權杖；權杖快取用 Fernet 加密存在 `user_mail_credential`，worker 只用寄件人本人的那一筆。失效時標成 `needs_reconnect`，暫停寄送並請業務重新連結（ADR 0005）。
- 不直接使用 SMTP：Exchange Online 正在淘汰 SMTP 基本驗證。
- 限速：每位寄件人每分鐘最多 N 封，每天最多 50 封，超過的自動排到隔天。
- 每封信的結尾都要有退訂說明。
- 真實寄信測試期間設定收件者白名單 `MAIL_ALLOWED_RECIPIENTS`（完整 email 或 `@網域`）：名單外的收件者在建立草稿和 worker 寄出前都會被擋下（原因 `RECIPIENT_NOT_ALLOWED`）。空白代表不限制，正式上線才清空（M2-18）。

---

## 8. 資料庫

PostgreSQL 16，完整的 DDL 在 [`backend/db/schema.sql`](../backend/db/schema.sql)。

### 8.1 資料表一覽
| 分組 | 資料表 | 用途 |
|---|---|---|
| 使用者 | `app_user` | 業務、主管、管理員 |
| 維度 | `dim_industry`、`dim_priority` | 18 類產業；A–D 優先級和星級的對照（取代 Excel 裡混在資料欄的圖例） |
| 名單 | `import_batch`、`company` | 匯入批次（預覽時把解析好的資料暫存在 `payload`，確認後才寫入）；公司主檔（統編唯一）、目前狀態、負責業務、業務修正的產業 `industry_override_id`；0009 起加上國別 `country`、網址狀態 `url_status`、資料來源 `source`，批次加上 MLE 附的漏斗數字 `funnel` |
| 模型 | `model_run`、`classification` | 每次模型 run 都保留一份分類結果，`is_current` 標示目前生效的那一份；0009 起加上適合度星等 `fit_stars`（1.0～5.0）、產品類型 `product_type`、命中標籤 `tags` |
| 回饋 | `review`、`gold_label` | 業務審核（排除一定要有原因）；`gold_label` 是原本盲標用的表，盲標已取消（2026-11-18），表保留未使用 |
| 聯絡 | `contact` | 聯絡人、來源（website／business_card／referral／exhibition／manual）和退訂狀態；同一家公司 email 不重複 |
| 郵件 | `email_template`、`campaign`、`email_draft`、`email_message`、`email_event` | 模板（`family_id` 串起各版本，修改就新增版本）→ 批次 → 草稿（業務編輯純文字 `body_text`，系統轉成 `body_html`；含原稿、排程時間、寄送嘗試次數、最後錯誤）→ 實際寄出 → 事件 |
| 成果 | `sales_case`、`case_update`、`activity_log` | 案件（編號 `case_no` C-0001；來源 `email`／`tracking`；狀態 sent／tracking／replied／negotiating／no_response／won／lost；下次追蹤日、成交金額；同一家公司同時只有一件未結案）→ 回填紀錄（管道、結果、備註、下次追蹤日、金額；系統事件管道為 `system`）；所有變更的稽核紀錄。原 `opportunity` 在 0006 移除 |
| 背景工作 | `job` | PostgreSQL 佇列（ADR 0003）：`kind`、`status`、`run_after`（排程與重試）、`attempts`；新增時 `NOTIFY job_queued` |
| 寄信權杖 | `user_mail_credential` | 每位業務一筆 Fernet 加密的 MSAL 權杖快取與連結狀態（ADR 0005） |
| 指標 | `v_recommendation`（0009 起含 `fit_stars`，沒給時用優先級星等）、`v_case_fact`（每件案件一列：是否寄出、回覆、成交、金額，0010）、`v_company_fact`（每家公司一列，名單漏斗，0010）、`v_kpi_summary`（0010 起回覆率 = 已寄出且有回覆的案件 ÷ 已寄出的案件，不讀 `email_event`）、`v_case_reminder`（待辦提醒，0007）、`v_funnel`、`v_win_rate_by_priority`、`v_reject_reasons` | **KPI 只在這些 view 定義一次** |

### 8.2 ER 關係（簡化）
```
app_user 1─* company(owner) 1─* classification *─1 model_run
company 1─* review          company 1─1 gold_label
company 1─* contact 1─* email_draft *─1 campaign *─1 email_template
email_draft 1─1 email_message 1─* email_event
company 1─* sales_case 1─* case_update     sales_case *─1 email_message
company 1─* activity_log
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

### 8.4 匯入 CSV 欄位規格 v1（MLE 與各成員共用）
會議決議：先把 CSV 欄位固定下來，各網站、各成員才能分頭產出同一種格式。欄位要收斂，只留看得懂、用得到的。

| 欄位（表頭用中文） | 程式欄位 | 必填 | 格式與規則 |
|---|---|---|---|
| 統編 | `tax_id` | 台灣公司必填 | 8 碼數字，左邊補 0。系統用它去重（國外公司見 11-6） |
| 公司名稱 | `name` | 是 | |
| 國別 | `country` | 否 | ISO 兩碼（TW、VN、TH、MY…），空白視為 TW |
| 官網 | `website_url` | 否 | 完整網址；沒有就留空 |
| 網址狀態 | `url_status` | 否 | `valid`／`invalid`／`unchecked`。`invalid` 的列在預覽中列為「略過」，不進名單 |
| 產業 | `industry` | 是 | 必須是 `dim_industry` 裡的名稱 |
| 產品類型 | `product_type` | 否 | 自由文字，例如「控制盤、PLC 盤」 |
| 命中標籤 | `tags` | 否 | 用「、」或「;」分隔，例如「自動化、電箱」 |
| 開發優先級 | `priority` | 是 | A／B／C／D（A 最高；會議上的 P1 = A） |
| 適合度星等 | `fit_stars` | 否 | 1.0～5.0，小數一位；空白時由優先級對照 |
| 資料來源 | `source` | 是 | 來源網站代號，例如 `expo`、`association`、`b2b` |
| 推薦理由 | `reason` | 否 | 一兩句話 |

- 原本 JULIA Excel 的欄位（使用可能性、分數、客戶屬性、登記產品）仍然接受，對照規則見 8.3。
- 多出來、看不懂的欄位會被忽略，並在預覽中提示。範例檔：`docs/samples/import_v1_sample.csv`（假資料）。
- 檔案有「資料來源」欄時每列都要填；舊版 Excel 沒有這一欄仍可匯入，預覽提示這批公司的來源會算在「未標示」，重新匯入也不會洗掉已知的來源。
- 漏斗前段的數字（資料庫總數、產業篩選後、網址有效、產品命中）由 MLE 在匯入時附上（API 匯入時放在 `funnel` 欄位），系統只顯示，不重算。

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
| **M2 寄信** | 模板、`template_only` 生成、預覽佇列、Graph 寄送（只用 `Mail.Send`）、防呆、限速 | 一位業務從核准到寄出 10 封信，全部出現在他的 Outlook 寄件備份 |
| **M3 案件追蹤與總覽（閉環）** | CSV v1 欄位、自動開案、人工回填、逾期催辦、總覽頁、欄位自選與匯出 | 用 100 筆名單寄出後，模擬一位客戶回覆並回填到成交，總覽頁的回覆率、成交數、待辦提醒都正確 |
| **M4 AI 寫信、績效與名單品質** | `template_ai` / `full_ai`（本機地端 LLM）、官網摘要、回覆態度分類、績效頁、排除原因報表 | 用本機 LLM 產生 50 封草稿並審核寄出（sandbox）；績效頁與排除原因報表可以比較各批名單 |
| **M5 延伸** | 來源管理、產品標籤維護、專用信箱轉寄自動比對回覆、BI 儀表板 | 依需要再定 |

---

## 11. 待確認事項

1. 優先級定義：Excel 圖例的順序和資料不完全一致。依 50 筆資料交叉比對，暫定 **A = 使用可能性高**、**B = 中、可開發**、**C = 中但需求不明確，或屬於策略／競合對象**、**D = 低（材料或純零件）**。唯一一筆「明確但競合」被評為 B，和「C 含競合」的說法互相矛盾，請業務主管確認競合對象應該歸在哪一級。
2. 每人每日寄送上限和鎖定天數（目前暫定 50 封、30 天）。
3. 部署位置：公司內網主機或雲端。改成人工回填後不需要 Graph webhook，內網主機也可以。
4. Microsoft 365 的租用戶管理員能不能核准這個應用程式的 `Mail.Send` 權限（已不需要 `Mail.Read`）。
5. 郵件模板的初版內容和法律聲明（退訂說明）由誰提供。
6. 國外公司（越南、泰國、馬來西亞…）沒有台灣統編，要用什麼當唯一鍵？建議 `國別 + 當地登記號碼`，沒有的話由 MLE 給一個固定的公司代號。
7. 適合度星等的算法（會議說法：產業 × 產品標籤 × 開發優先級）由 MLE 決定並寫進 CSV；系統只負責顯示。
8. 催辦提醒的管道：第一版只出現在平台的待辦清單；要不要另外每天寄一封摘要信給業務？
9. 推薦名單的最小單位：大類產業，還是更細的產品層級（會議提出，尚未定案）。
10. 地端 LLM 的 GPU 主機：待公司 IT 確認。確認前 M4 先用開發機本機能跑的 Ollama＋`qwen3:8b`／`qwen3:14b` 開發與試行，自動化測試用 `FakeLlmClient`（2026-11-18）。
11. 寄信時要不要自動認領公司（目前只有「認領」和「加入追蹤」會），請業務主管決定（M3-14 發現）。
