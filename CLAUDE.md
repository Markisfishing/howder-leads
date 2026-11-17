# 厚達電子 潛在客戶推薦與邀請信系統

協助厚達電子（端子台製造商）業務部的內部 Web 系統。主要功能：
1. 把 MLE 模型評分後的潛在客戶，以星級排序呈現。
2. 讓業務審核要合作的對象。
3. 批次產生邀請信，經業務預覽、核准後，從業務本人的 Outlook 寄出。
4. 追蹤回覆與成效，並把結果回饋給 MLE。

完整規格見 `docs/SPEC.md`。**規格和本檔衝突時，以本檔為準，並回報使用者，讓他決定要不要更新 SPEC。**

---

## 1. 資料夾結構

```
frontend/                 前端（業務頁 + 管理頁在同一個 SPA，用角色控管 /admin/*）
  src/
    pages/                一個路由一個頁面元件（對應 SPEC 6.2）
    components/           跨頁共用元件（Button、Tag、Stars、DataTable…）
    api/                  呼叫後端的函式與型別，頁面不直接寫 fetch
    styles/
      design-tokens.css   ★ 設計規範，唯一可以寫具體色碼與數值的檔案
  prototypes/             靜態 HTML 原型（設計確認用，不會上線）
backend/                  後端 API + 背景 Worker（同一個 Python 套件）
  app/
    api/v1/               FastAPI 路由：只做輸入驗證、權限檢查、呼叫 domain/services
    domain/               商業規則：狀態機、寄送防呆、鎖定規則（不 import FastAPI 或 SQLAlchemy）
    services/             對外整合與流程：importer、generator(Claude)、mailer(Graph)、metrics
    workers/              背景工作（PostgreSQL 佇列，ADR 0003）：generate_drafts、send_scheduled、sync_replies
    models/               SQLAlchemy ORM
    prompts/              AI 郵件 prompt，檔名帶版本（invite_v1.md）
  db/schema.sql           資料庫參考 DDL（M1 導入 Alembic 後，以 migrations 為準）
  tests/
docs/
  SPEC.md                 規格書（靜態藍圖）
  adr/                    架構決策紀錄（0001-xxx.md）
PROGRESS.md               ★ 動態進度：任務清單 [ ] / [x]，記錄現在做到哪裡
CHANGELOG.md              ★ 開發日誌：每個階段改了什麼、下一步是什麼
```

**用語約定：** 資料夾叫 `frontend` / `backend`，不叫 client / admin。管理頁只是同一個前端裡的 `/admin/*` 路由，不另外做一個專案。拆成兩個專案的話，登入、元件、樣式都要維護兩份。

---

## 2. 專有名詞（程式命名、UI 文字、討論時都要一致）

| 中文（UI 顯示） | 程式命名 | 說明 |
|---|---|---|
| 公司 | `company` | 一個統編一筆，`tax_id` 是業務上的唯一鍵 |
| 推薦度 / 星級 | `stars`（由 `priority` A–D 對照） | 對照表在 `dim_priority`，不要寫死在程式裡 |
| 審核：通過 / 排除 | `review`、`approved` / `rejected` | 排除一定要有 `reject_reason` |
| 認領 | `owner_id` + `owner_locked_until` | 鎖定期間其他業務不能寄信給這家公司 |
| 邀請信批次 | `campaign` | |
| 草稿 | `email_draft` | AI 原稿存在 `ai_original` |
| 寄出的信 | `email_message` | 只有核准的草稿才會變成這個 |
| 模型版本 | `model_run` / `run_id` | 每次 MLE 匯入就是一個 run |
| 盲標 | `gold_label` | 標準答案，標的人看不到模型結果 |

UI 文字用繁體中文；程式識別字（變數、函式、資料表、API 路徑）用英文；程式註解用繁體中文。

---

## 3. 技術棧與指令

| 層 | 技術 |
|---|---|
| 前端 | React 19 + TypeScript (strict) + Vite、React Router、TanStack Query / Table、Radix UI Primitives（無樣式）、CSS Modules + design tokens |
| 後端 | Python 3.12、FastAPI、Pydantic v2、SQLAlchemy 2、Alembic；背景工作用 PostgreSQL 佇列（`SKIP LOCKED`，見 ADR 0003），不用 Redis |
| 資料庫 | PostgreSQL 16 |
| 外部服務 | Claude API（產生郵件）、Microsoft Graph（登入、寄信、讀回覆） |
| 部署 | Docker Compose（Nginx + frontend 靜態檔 + api + worker + postgres） |

指令（專案骨架建好後補上實際指令；**新增或修改指令時一併更新這一段**）：

```bash
# 原型預覽：http://127.0.0.1:5510/prototypes/recommendations.html
python -m http.server 5510 --bind 127.0.0.1 --directory frontend

# 後端（在 backend/ 底下；第一次先 `uv sync`，並把 .env.example 複製成 .env）
uv run python -m scripts.dev_db          # 不用 Docker 的開發資料庫，印出 DATABASE_URL 填進 .env，保持執行
uv run alembic upgrade head              # 套用 migration
uv run uvicorn app.main:app --port 8000  # API：http://127.0.0.1:8000/api/v1
uv run pytest                            # 測試（自己會開一個暫時的 Postgres，不碰開發資料庫）
uv run ruff check . && uv run ruff format --check . && uv run mypy app

# 前端（在 frontend/ 底下；第一次先 `npm install`）
npm run dev        # http://127.0.0.1:5173，/api 轉到 8000
npm run typecheck && npm run lint && npm run test && npm run build
```

> 專案路徑有中文：`scripts/pg_local.py` 會把 Postgres 執行檔複製到 `%LOCALAPPDATA%\howder\` 再啟動（initdb 不吃非 ASCII 路徑）；`alembic.ini` 只能寫 ASCII（configparser 用系統編碼讀檔）。

---

## 4. 架構規則

1. **前端只透過 `/api/v1` 取資料**，頁面元件不直接寫 `fetch`，一律經過 `frontend/src/api/`。
2. **`domain/` 是純 Python**，不 import FastAPI、SQLAlchemy 或任何外部 SDK，才能直接寫單元測試。
3. **公司狀態只能透過 `domain` 的狀態機函式改變**，不可以直接 `company.status = ...`。每次變更都要寫一筆 `activity_log`。
4. **KPI 只在資料庫 view（`v_*`）定義一次**。後端 `metrics` 只讀取 view，前端只負責顯示，不重算比例。
5. **外部服務一律包在 `services/` 裡**（Claude、Graph），並且透過介面注入，測試時可以換成假的實作。
6. **耗時的工作放進 worker**（產生草稿、寄信、同步回覆），API 只回傳 `job_id`，不在 request 裡等待。
7. API 錯誤統一用 `{ "error": { "code": "UPPER_SNAKE", "message": "…" } }` 格式；`code` 要能讓前端對應到中文訊息。

---

## 5. 資料庫規則

1. **M1 導入 Alembic 之後，schema 只能透過 migration 修改**。已經套用過的 migration 不可以再改，要改就新增一個。
2. 修改 schema 時，要同步更新 `backend/db/schema.sql`（參考用）和 `docs/SPEC.md` 第 8 節的資料表一覽。
3. 狀態、原因這類固定選項，用 enum 或 CHECK 約束，不要只靠前端檢查。
4. 刪除資料預設用軟刪除或改狀態。只有「個資刪除請求」可以真的刪除，而且要寫 `activity_log`。
5. 時間一律存 `TIMESTAMPTZ`（UTC），由前端轉成台灣時間顯示。

---

## 6. 寄信與 AI 安全規則（最重要，不可違反）

1. **系統絕對不會自動寄信。** 只有 `status = approved` 的草稿可以寄，後端寄送前要再檢查一次，不能只靠前端把按鈕藏起來。
2. 寄送防呆一律在後端 `domain` 實作：已退訂、`do_not_contact`、被其他業務鎖定、14 天內寄過的對象都要排除。
3. **開發和測試環境不可以真的寄信。** `MAIL_MODE=sandbox` 時，信件只寫進資料庫或 log。只有 `MAIL_MODE=live` 才會呼叫 Graph `sendMail`，而且只能在正式環境設定。
4. 自動化測試不可以呼叫真實的 Claude 或 Graph API，一律用假的實作。
5. AI prompt 放在 `backend/app/prompts/`，檔名要帶版本。修改 prompt 就新增一個版本，不覆蓋舊檔，這樣才能對照 `ai_original` 是哪一版產生的。
6. Prompt 必須要求模型：不捏造客戶實績、價格、認證或交期，內容只能根據提供的公司資料撰寫。
7. **盲標 API 的回應不可以包含任何模型欄位**（priority、stars、score、reason、industry 預測），寫測試驗證這一點。

---

## 7. 前端與樣式規則

1. **顏色、字級、間距一律用 `frontend/src/styles/design-tokens.css` 的變數**，其他檔案不可以出現 `#` 色碼或寫死的 px。
2. **不要修改 `design-tokens.css`**，除非使用者明確要求改哪一個值。需要新的 token 時，先問使用者。
3. 不引入帶樣式的 CSS 框架或元件庫（Tailwind、Bootstrap、MUI、Ant Design…）和外部字型。元件的互動行為和無障礙（對話框、下拉選單、側欄、Tooltip）用 **Radix UI Primitives**，外觀一律自己用 tokens 寫。
4. 先寫手機版，再用 `@media (min-width: 768px)` 和 `(min-width: 1024px)` 往上加寬螢幕的規則。
5. 元件樣式用 **CSS Modules**（`Xxx.module.css` 和元件放在同一個資料夾）。全域樣式只放在 `src/styles/global.css`，`* { box-sizing: border-box; }` 寫在那裡一次就好。
6. 每個頁面都要處理四種狀態：載入中、空資料、錯誤、正常。
7. 無障礙：文字對比 ≥ 4.5:1、可以只用鍵盤完成審核和核准、圖示按鈕要有 `aria-label`、星級旁邊一定要附等級文字。
8. 用 `prototypes/` 裡的原型確認設計；正式頁面寫在 `src/pages/`，不要直接修改原型拿來上線。

---

## 8. 資料與個資

1. **不可以把真實的聯絡人姓名、email、電話放進程式碼、測試資料或範例**，一律用假資料（例如 `contact@example.com`）。
2. 原始名單 Excel（`D:\資料侠\厚達_50家客戶_*.xlsx`）不複製進專案。測試用的種子資料只放公司層級的公開資訊（公司名、產業），或用假資料。
3. 機密資訊（API key、Graph client secret、資料庫密碼）只放在 `.env`，不 commit；提供 `.env.example` 列出需要哪些變數。
4. Log 不可以印出 email 全文、權杖或 API key。

---

## 9. 測試規則

1. `domain/` 的每一條規則都要有單元測試：狀態機的合法與非法轉換、寄送防呆、鎖定規則。
2. API 至少要測：權限（業務不能呼叫 `/admin`）、未核准的草稿不能寄、盲標 API 不含模型欄位、重複匯入不會新增公司。
3. 修 bug 時，先寫一個能重現 bug 的測試，再修。
4. 前端用 Vitest 測試 `api/` 和有邏輯的元件；畫面外觀用原型和瀏覽器檢查。
5. 新功能必須附測試，**每一條驗收條件至少一個 test**，test 名稱帶需求 ID（例如 `test_f_mail_7_*`）。純樣式或畫面調整不強制寫 test，改用瀏覽器檢查。功能和它的測試放在同一個 commit。

---

## 10. Commit 規則

1. 分段 commit，一個功能改動一次 commit。
2. Commit 訊息以繁體中文為主，專有名詞才用英文，並包含前綴：
   - `feat:` 新功能、`fix:` 修 bug、`refactor:` 重構、`docs:` 文件、`test:` 測試、`style:` 樣式、`chore:` 雜項
   - 範例：`feat: 推薦清單加入批次排除與原因選擇`
3. 前端、後端、文件的改動如果屬於同一個功能，可以放在同一個 commit；不相關的改動要分開。
4. Schema 變更（migration）單獨一個 commit。
5. 分支命名：`feat/xxx`、`fix/xxx`、`docs/xxx`，不直接在 `main` 開發。

---

## 11. 開發流程

1. 除了完成該次任務，也要審查相關內容是否還有可以優化的地方。**發現的問題先列出來給使用者，不要順手大改範圍外的程式。**
2. 動手前先確認這個功能在 `docs/SPEC.md` 的需求 ID（例如 F-MAIL-5），並在 PR 或 commit 說明中寫出來。
3. 做了架構上的選擇（換套件、改資料流）時，在 `docs/adr/` 新增一份短 ADR：背景、決定、理由。
4. 完成前的檢查清單：
   - [ ] 後端 lint、型別檢查、測試都通過
   - [ ] 前端 lint、typecheck、測試都通過
   - [ ] 有畫面改動的話，375px 和 1280px 寬都在瀏覽器實際看過
   - [ ] 樣式檔沒有寫死色碼或 px
   - [ ] 影響到規格的話，`docs/SPEC.md` 已經同步更新
   - [ ] `PROGRESS.md` 已勾選並填上日期（見第 13 節）
   - [ ] 沒有 commit `.env`、真實聯絡人資料或原始 Excel

---

## 12. 禁止事項

- 不可以加入任何自動寄信、跳過核准、繞過寄送防呆的程式路徑，包括「測試用」的捷徑。
- 不可以在測試或開發環境使用真實的客戶 email。
- 不可以修改已經套用過的 migration。
- 不可以在 `design-tokens.css` 以外的地方寫死顏色。
- 不可以把模型預測欄位加進盲標 API。
- 不可以刪除使用者已經寫好、但這次任務沒有要求修改的程式或文件。

---

## 13. 進度與開發日誌（每次都要做）

三份文件各管一件事：`docs/SPEC.md` 是**要做什麼**（很少改）、`PROGRESS.md` 是**做到哪裡**（每個任務都改）、`CHANGELOG.md` 是**怎麼走到這裡**（每個階段新增一則）。

**開始工作前**
1. 先讀 `PROGRESS.md` 頂端的狀態表，以及 `CHANGELOG.md` 最上面一則，再動手。
2. 使用者沒有指定任務時，從 `PROGRESS.md` 的「下一個任務」開始，並先告訴使用者要做哪一個。

**每完成一個任務**（強制，不需要使用者提醒）
1. 在 `PROGRESS.md` 把該任務的 `[ ]` 改成 `[x]`，行尾加上 ` — YYYY-MM-DD`。
2. 更新頂端狀態表的「最後更新」「目前階段」「下一個任務」「卡住 / 待確認」。
3. 進度更新和該功能放在**同一個 commit**。
4. 只完成一部分的話不要打勾，改在任務後面註記 `（進行中：已完成 xxx）`。

**任務清單的維護**
- 任務大小以「一次對話、一個 commit 做得完」為準，太大就拆成 `M1-16a`、`M1-16b`。
- 開發中發現新的工作，加到該階段最後面，或加到「開發中發現、還沒排進階段的事」。**不要刪除任務**；不做了就改成 `- [~] … （取消：原因）`。
- 任務編號一旦給出就不重新編號，以免 commit 和日誌裡的引用對不上。
- 開始做 M2 以後的階段前，先把該階段拆成和 M1 一樣細的任務。

**每結束一個階段或一次對話**
在 `CHANGELOG.md` **最上面**新增一則，標題 `## YYYY-MM-DD｜做了什麼`，內容固定五段：
1. **改了哪些檔案**（路徑加一句說明）
2. **解決了什麼問題**
3. **做了哪些決定**（重大的另外寫 ADR）
4. **還沒處理的問題**
5. **下一步**（對應 `PROGRESS.md` 的任務編號）

舊的日誌不修改、不刪除；寫錯的話，在新的一則裡更正。
