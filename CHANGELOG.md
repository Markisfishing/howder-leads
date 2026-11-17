# 開發日誌

> 每結束一個開發階段（或一次對話）就在**最上面**新增一則。開新對話時，先讀最上面一則和 `PROGRESS.md`，就能接上進度。
> 格式固定五段：改了哪些檔案、解決了什麼問題、做了哪些決定、還沒處理的問題、下一步。

---

## 2026-11-17｜M1 MVP：匯入、推薦清單、審核

**改了哪些檔案**
- `backend/`：FastAPI 專案（uv 管理）
  - `app/config.py`、`errors.py`、`db.py`、`main.py`：設定、統一錯誤格式、資料庫連線
  - `app/api/v1/`：users、imports、companies、reviews、meta 路由
  - `app/domain/company_rules.py`：狀態機、排除原因、認領鎖定（純 Python）
  - `app/services/`：importer、company_service、auth（Entra token 驗證）
  - `app/models/`：ORM
  - `migrations/`：0001 初始 schema、0002 回覆率
  - `scripts/pg_local.py`、`scripts/dev_db.py`：內嵌 Postgres
  - `tests/`：78 個測試
- `frontend/`：Vite + React 19 + TS strict
  - `src/api/`：唯一的 fetch 入口、錯誤碼中文化、React Query hook
  - `src/auth/`：dev／Entra 登入
  - `src/components/`：Button、Tag、Stars、StateView、Modal、AppLayout
  - `src/pages/`：推薦清單、公司詳情、名單匯入、登入
  - `scripts/check-styles.mjs`：擋寫死色碼與 px
  - Vitest：15 個測試
- `docs/adr/0001`（內嵌 Postgres）、`0002`（手寫 SQL migration）：新增
- `docs/SPEC.md`：資料表、API 表同步；F-IMP-2 補上錯誤列規則；修正表格跳脫
- `CLAUDE.md`：第 3 節換成實際指令
- `PROGRESS.md`：M1 打勾，新增 6 個待辦

**解決了什麼問題**
- MLE 名單可以用 CSV／XLSX 上傳或 JSON API 匯入，先預覽再確認，以統編去重，每次匯入都是一個模型版本。
- 業務可以在推薦清單上：
  - 依星級篩選與排序
  - 批次通過或排除（排除一定要選原因）
  - 認領公司（鎖定 30 天）
  - 在側欄修正官網與產業
  - 手動加入公司
- 管理員可以下載審核結果 CSV，交給 MLE。
- 用原始 50 家 Excel 在本機走完一輪：49 家匯入、1 列缺統編被擋下，重複匯入 0 新增。資料只在本機資料庫，沒有進 repo。
- 375px 與 1280px 都沒有橫向捲軸，審核流程可以只用鍵盤完成。

**做了哪些決定**
- 開發與測試用內嵌 Postgres，不依賴 Docker（ADR 0001）。
- Migration 手寫 SQL，KPI 只在 view 定義（ADR 0002）。
- 畫面匯入會略過有錯的列、其他照常寫入；API 匯入有錯就整批拒絕（已寫進 SPEC F-IMP-2）。
- 批次審核全有或全無：只要一家不能改，整批都不改，並列出原因。
- 業務修正過的官網，之後的匯入不會覆蓋；產業修正存在 `company.industry_override_id`，不改模型原判。
- 前端版本比較新（TS 6、Vite 8、ESLint 10、Vitest 5、MSAL 5）：
  - MSAL 5 沒有 `createPublicClientApplication`，改用 constructor 加 `initialize()`。
  - `react-hooks/purity` 不允許在 render 時呼叫 `Date.now()`，鎖定判斷抽成 `lib/ownership.ts`。

**還沒處理的問題**
- M1-03：這台電腦的 Docker Desktop 無法啟動，`docker-compose.yml` 還沒驗證。
- Entra 登入只用自簽金鑰做過單元測試，還沒接過真實租用戶（要等 SPEC 11-4 權限核准）。
- 優先級 C 的定義還沒確認（SPEC 11-1）。
- `PROGRESS.md`「開發中發現」新增 6 項：
  - bundle 大小
  - 手機篩選列太長
  - Excel 第 44 列缺統編
  - 側欄初始焦點
  - CSV 時區
  - 頁面元件測試

**下一步**
- 依 CLAUDE.md 第 13 節，先把 M2（寄信）拆成和 M1 一樣細的任務，再從 Graph 寄信（`MAIL_MODE=sandbox`）開始。
- 能用 Docker 的時候補做 M1-03。

---

## 2026-11-17｜M0 規劃與設計完成

**改了哪些檔案**
- `docs/SPEC.md`：新增規格書（目標、角色、流程與狀態機、功能需求和驗收條件、架構、前後端、資料庫、非功能需求、開發階段、待確認事項）
- `backend/db/schema.sql`：新增 PostgreSQL schema，包含 17 張表、4 個指標 view 和 A–D 種子資料
- `frontend/src/styles/design-tokens.css`：新增配色、字級、間距規範
- `frontend/prototypes/recommendations.html`、`.css`：新增推薦清單頁靜態原型
- `CLAUDE.md`：重寫成這個專案的開發規則（原本的內容是別的專案的）
- `.gitignore`、`PROGRESS.md`、`CHANGELOG.md`：新增
- 建立 `frontend/`、`backend/`、`docs/adr/` 資料夾骨架

**解決了什麼問題**
- 原始 Excel 的資料問題：
  - 「端子台使用可能性」混了競合，拆成 `likelihood` 和 `is_competitor` 兩欄。
  - 「建議動作」和優先級重複，改成由優先級推導。
  - 「分類／家數」是混在資料欄裡的圖例，改成獨立的 `dim_priority` 表。
- 定案業務端的完整流程：推薦 → 審核 → 產生草稿 → 預覽核准 → 寄出 → 追蹤 → 回饋給 MLE。

**做了哪些決定**
- 做成 Web，不做桌面軟體。理由是多人共用名單、要有中央紀錄、要串 Outlook。
- 寄信用 Microsoft Graph，不直接用 SMTP。這樣信會從業務本人的信箱寄出，也能讀到回覆。
- 資料夾叫 `frontend` / `backend`。管理頁只是前端裡的 `/admin/*` 路由，不另外做專案。
- 配色：品牌紅降彩度成磚紅 `#B4433A` 當主色，淺色暖白底。
- 前端：無樣式的 Radix UI Primitives 加上 CSS Modules，不使用帶樣式的元件庫。
- 星級對照：A=5 星、B=4 星、C=2 星、D=1 星。

**還沒處理的問題**
- 優先級 C 的定義和「競合」該歸在哪一級，要等業務主管確認（SPEC 11-1）。
- 每日寄送上限、鎖定天數、部署位置、Microsoft 365 權限核准、模板內容都還沒定案（SPEC 11-2 到 11-5）。

**下一步**
- M1-01 建立後端專案骨架，接著依 `PROGRESS.md` 的 M1 順序進行。
