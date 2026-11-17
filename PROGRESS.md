# 開發進度

> 這份檔案記錄「現在做到哪裡」。規格看 `docs/SPEC.md`，每個階段做了什麼看 `CHANGELOG.md`。
> 規則（CLAUDE.md 第 13 節）：每完成一個任務就把 `[ ]` 改成 `[x]`，並在行尾加上完成日期，同時更新下方的「最後更新」。

| 項目 | 狀態 |
|---|---|
| 最後更新 | 2026-11-17 |
| 目前階段 | **M1 MVP（功能完成；只剩 M1-03 Docker 驗證）** |
| 下一個任務 | 把 M2 拆成和 M1 一樣細的任務，從 Graph 寄信（sandbox）開始 |
| 卡住 / 待確認 | 優先級 C 的定義（SPEC 11-1）、Microsoft 365 管理員是否核准應用程式權限（SPEC 11-4）、Docker Desktop 無法啟動（M1-03） |

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
- [ ] M1-03 `docker-compose.yml`：postgres 16 + redis（開發用）（進行中：已寫 docker-compose.yml，但 Docker Desktop 在這台電腦無法啟動、未驗證；開發與測試改用 backend/scripts/dev_db.py 內嵌 Postgres）
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

## M2 寄信（之後再拆細）

- [ ] M2-01 聯絡人 CRUD
- [ ] M2-02 郵件模板管理（admin）
- [ ] M2-03 建立 campaign＋`template_only` 草稿產生（F-MAIL-1、F-MAIL-2）
- [ ] M2-04 寄送防呆 domain 規則＋測試（F-MAIL-7）
- [ ] M2-05 預覽佇列頁（F-MAIL-4）
- [ ] M2-06 只有核准的草稿可以寄＋測試（F-MAIL-5）
- [ ] M2-07 Graph `sendMail`（`MAIL_MODE=sandbox` / `live`）、每日上限、排程（F-MAIL-6）
- [ ] M2-08 計算改稿幅度 `edit_ratio`（F-MAIL-8）

## M3 AI 與追蹤（之後再拆細）

- [ ] M3-01 prompt `invite_v1`＋`template_ai` / `full_ai` 生成（F-MAIL-2、F-MAIL-3）
- [ ] M3-02 Graph 收件匣訂閱與回覆比對（F-TRK-1）
- [ ] M3-03 回覆態度分類（F-TRK-2）
- [ ] M3-04 退信與退訂處理（F-TRK-3）
- [ ] M3-05 商機階段與金額（F-TRK-4）

## M4 績效與回饋（之後再拆細）

- [ ] M4-01 績效頁：漏斗、各星級成交率、模板回覆率、業務排行（F-TRK-5）
- [ ] M4-02 排除原因報表（F-MLE-1）
- [ ] M4-03 回饋資料匯出（F-MLE-2）
- [ ] M4-04 盲標工作台＋「不含模型欄位」測試（F-MLE-3）
- [ ] M4-05 模型品質頁（F-MLE-4）

---

## 開發中發現、還沒排進階段的事

- [x] 新增 `.gitattributes` 統一 LF 換行（部署到 Linux 前） — 2026-11-17
- [ ] 前端 bundle 651 kB（超過 500 kB 警告）：dev 模式不需要 MSAL，可改成動態載入或依路由切分
- [ ] 手機版篩選列有 8 個欄位，佔掉一整個螢幕；考慮收合成「篩選」按鈕
- [ ] 原始 Excel 第 44 列缺統編，匯入時會被略過；請 MLE 或業務補上
- [ ] 公司詳情側欄打開時焦點落在「排除…」按鈕，改成落在標題或關閉鈕比較安全
- [ ] 審核結果 CSV 的時間是 UTC ISO 格式，確認 MLE 是否需要台灣時間
- [ ] `RecommendationsPage` 與 `AdminImportsPage` 尚無元件測試（目前靠瀏覽器檢查），M2 前補上
