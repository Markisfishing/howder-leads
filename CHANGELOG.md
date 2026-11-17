# 開發日誌

> 每結束一個開發階段（或一次對話）就在**最上面**新增一則。開新對話時，先讀最上面一則和 `PROGRESS.md`，就能接上進度。
> 格式固定五段：改了哪些檔案、解決了什麼問題、做了哪些決定、還沒處理的問題、下一步。

---

## 2026-11-17｜M2-10、M2-11、M2-01 聯絡人管理

**改了哪些檔案**
- `docs/adr/0005-outlook-delegated-token.md`：Outlook 寄信權杖用 On-Behalf-Of，Fernet 加密存放（M2-10）
- `backend/migrations/versions/0003_job_queue_and_mail_credential.py`：`job` 佇列、`user_mail_credential`、草稿寄送欄位、`campaign.status` CHECK（M2-11）
- `backend/migrations/versions/0004_contact_source_check.py`：聯絡人來源 CHECK（M2-01a）
- `backend/app/domain/contact_rules.py`：email 正規化與格式、來源白名單、刪除原因
- `backend/app/services/contact_service.py`、`backend/app/api/v1/contacts.py`：`POST /contacts`、`PATCH /contacts/{id}`、`POST /contacts/{id}/unsubscribe`、`DELETE /contacts/{id}`
- `backend/tests/test_contacts.py`、`test_schema_0003.py`、`test_schema_0004.py`
- `frontend/src/pages/recommendations/ContactsSection.tsx`、`ContactDialog.tsx`、`ContactConfirmDialog.tsx`、`Contacts.module.css`：側欄管理聯絡人（M2-01b）
- `frontend/src/api/*`：聯絡人 endpoints／hooks／錯誤訊息；`api()` 支援 204
- `frontend/src/lib/labels.ts`：聯絡人來源與往來紀錄中文
- `docs/SPEC.md`：8.1 資料表、7 API 一覽同步

**解決了什麼問題**
- 寄信前一定要有聯絡人：現在可以在側欄新增、編輯，來源必填，同一家公司 email 不重複（大小寫視為同一個）。
- 退訂（F-CASE-5）：聯絡人改成已退訂，公司同時改成「不再聯絡」；不受認領鎖定限制，任何業務收到都能標記。
- 個資刪除（SPEC 9）：真的刪除聯絡人與寄給他的草稿、信件、事件；`activity_log` 只記原因和刪了幾封，不留姓名或 email。

**做了哪些決定**
- 聯絡人來源固定五種：公司官網、名片、別人介紹、展覽、其他（手動輸入）。
- 個資刪除只有主管／管理員能做，而且一定要填原因；前端再加一個「我了解無法復原」勾選。
- 一位聯絡人退訂就把整家公司改成 `do_not_contact`（依 SPEC F-CASE-5）；公司已成交（won）時只標記聯絡人。
- 已退訂的聯絡人不能改 email，也沒有「取消退訂」的入口。
- 郵件表還沒有 ORM，刪除個資時直接用 SQL；M2-02 之後加 ORM 再改寫。

**還沒處理的問題**
- 「取消退訂」要不要做、由誰做（已記在 PROGRESS 的「開發中發現」）。
- 一位聯絡人退訂就封鎖整家公司，對大公司（多個窗口）可能太嚴，請業務主管確認。
- M1-03 Docker 驗證仍卡在 Docker Desktop。

**下一步**
- M2-02a 郵件模板後端 `/templates`。

---

## 2026-11-17｜M2 拆細、佇列改 PostgreSQL、依會議調整規格

**改了哪些檔案**
- `PROGRESS.md`
  - M2 拆成 a/b/c 子任務，新增 M2-09～15
  - M3 改成「案件追蹤與總覽（閉環）」，新增 M3-06～15
  - M3-01、02、03、05 改成取消或移到 M4，並寫明原因
  - 新增 M5 延伸
- `docs/adr/0003-postgres-job-queue.md`：背景工作改用 PostgreSQL 佇列
- `docs/adr/0004-manual-reply-backfill.md`：回覆改人工回填，每封開發信開一個案件
- `docs/SPEC.md`（v0.2）
  - 新增 4.4 案件追蹤與催辦（F-CASE-1～5）、4.6 總覽（F-DASH-1～4）、4.7 來源與標籤（延伸）
  - 新增 F-REC-7～9
  - 新增 8.4 CSV 欄位規格 v1
  - 路由與 API 補上案件、總覽
  - Graph 只申請 `Mail.Send`
  - 第 10 節階段重排，第 11 節新增 6～9
- `CLAUDE.md`
  - 技術棧拿掉 Redis
  - 專有名詞補上 `fit_stars`、`source`、`sales_case`、`case_update`、`reminder`
- `docker-compose.yml`：拿掉 redis

**解決了什麼問題**
- 這台電腦跑不了 Redis，背景工作改放 PostgreSQL，不必多裝服務。
- 對照 2026-11-17 會議記錄，規格補上這些漏掉的部分：
  - 人工回填與逾期催辦
  - 案件
  - 資料來源、國別、網址狀態、產品類型、命中標籤
  - 小數星等
  - 總覽頁
  - 欄位自選與匯出

**做了哪些決定**
- 佇列用 `SELECT … FOR UPDATE SKIP LOCKED`（ADR 0003）。
- 不讀業務信箱，Graph 只申請 `Mail.Send`；第一版回覆一律人工回填；之後自動化改用專用信箱轉寄（ADR 0004）。
- 星等由 MLE 算好放進 CSV，系統只顯示。
- 階段順序改成：M2 寄信 → M3 案件追蹤與總覽 → M4 AI 寫信與績效 → M5 延伸。

**還沒處理的問題**
- 待確認（SPEC 第 11 節）：
  - 國外公司的唯一鍵（11-6）
  - 星等算法（11-7）
  - 催辦要不要另外寄每日摘要信（11-8）
  - 推薦名單的最小單位（11-9）
- `opportunity`、`sales_case`、CSV v1 新欄位都還只是規劃，migration 還沒寫。

**下一步**
- M2-10：Outlook 委派權杖（只用 `Mail.Send`）的 ADR。
- M2-11：migration 0003，建立 `job`、`user_mail_credential` 和寄送欄位。

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
