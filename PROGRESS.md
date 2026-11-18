# 開發進度

> 這份檔案記錄「現在做到哪裡」。規格看 `docs/SPEC.md`，每個階段做了什麼看 `CHANGELOG.md`。
> 規則（CLAUDE.md 第 13 節）：每完成一個任務就把 `[ ]` 改成 `[x]`，並在行尾加上完成日期，同時更新下方的「最後更新」。

| 項目 | 狀態 |
|---|---|
| 最後更新 | 2026-11-18（M4 併入 feat/m1-mvp） |
| 目前階段 | **M4 大部分完成**：績效頁、名單品質、回覆態度、官網摘要、AI 寫信（`template_ai`／`full_ai`、本機 `qwen3:8b`）都做完並有測試；M4-06 還剩 b（業務盲評）、g（`CLAUDE.md` 指令補充）、l（完整 sandbox 50 封驗收）。M3 全部完成。M2 剩 M2-17，以及真實寄信（先用個人 Microsoft 帳號：M2-19～M2-21 → M2-15；M2-22 已完成）；M1 只剩 M1-03 Docker 驗證 |
| 下一個任務 | **接手的人先看下方「交接：剩下的任務怎麼做」**。M2-19 ADR：個人 Microsoft 帳號登入與寄信（先確認做法再寫程式）；M2-23 拿掉介面上的「模型」用語；M2-17；M4-06b 業務盲評（要業務來做）；M4-06g 問使用者後補 `CLAUDE.md` 第 3 節指令；M4-06l 完整 sandbox 驗收；之後 M5 |
| 卡住 / 待確認 | 個人帳號能不能註冊應用程式（M2-19）、匯入批次漏斗數字與 `gold_label` 表要不要移除（見「開發中發現」）、寄信時要不要自動認領公司（SPEC 11-11）、公司地端 LLM GPU 主機（SPEC 11-10；M4 先用本機 Ollama＋qwen3）、優先級 C 的定義（SPEC 11-1）、國外公司唯一鍵（SPEC 11-6）、Docker Desktop 無法啟動（M1-03）。公司 Microsoft 365 帳號之後再說（SPEC 11-4） |

格式：`- [ ] 編號 任務（需求 ID）` → 完成後 `- [x] 編號 任務（需求 ID） — YYYY-MM-DD`
一個任務的大小以「一次對話、一個 commit 做得完」為準；太大就拆開。

---

## 交接：剩下的任務怎麼做（2026-11-18 整理，給接手的人）

> 下面每一張卡片寫清楚：誰能做、前置、要改哪些檔案、步驟、驗收與測試。任務清單本身（`[ ]`／`[x]`）仍在各階段底下，做完照 CLAUDE.md 第 13 節打勾、填日期、更新上方狀態表。

### 開工前必讀
- **規則**：先讀 `CLAUDE.md`（以它為準）、`docs/SPEC.md`、`CHANGELOG.md` 最上面一則。最重要的幾條：
  - 系統絕對不自動寄信；只有 `approved` 草稿能寄，後端寄前再檢查（第 6 節）。
  - 測試環境不可以真的寄信；開發環境要 `MAIL_ALLOWED_RECIPIENTS` 不是空的才可以 `MAIL_MODE=live`（第 6 節第 3 點，M2-22 已實作在 `backend/app/config.py` 的 `_guard_production`）。
  - 自動化測試不可以連真實的 LLM 或 Microsoft；一律用假的實作（`FakeLlmClient`、`tests/test_mail_connection.py` 的 `FakeObo` 等）。
  - 不可以把真實的姓名、email、電話放進程式、測試、範例或這份文件；真實信箱只寫在 `backend/.env`（不 commit）。
  - 密碼、client secret、`MAIL_TOKEN_KEY`、API key 只放 `.env`，不貼進對話、不 commit。**系統不使用任何信箱密碼**：寄信是用 Microsoft 登入授權（OAuth），帳號擁有人自己在 Microsoft 頁面登入、按同意。
  - 不改 `frontend/src/styles/design-tokens.css`；樣式不寫死色碼或 px；不用 prettier（專案沒有用，會改到不相關的行）。
  - 已套用的 migration 不能改；schema 變更單獨一個 commit，並同步 `backend/db/schema.sql` 與 SPEC 第 8 節。
- **分支**：目前在 `feat/m1-mvp`（M4 已併入，還沒 push）。接手的人要先拿到這個分支；push 與否由專案負責人決定。新任務開 `feat/xxx` 或 `fix/xxx` 分支。
- **開發環境**（指令細節見 CLAUDE.md 第 3 節）：
  - 資料庫：`cd backend && uv run python -m scripts.dev_db`（內嵌 Postgres，資料在 `%LOCALAPPDATA%\howder\pgdata`；要全新的空資料庫就設 `HOWDER_PGDATA` 指到另一個純英文路徑）→ `uv run alembic upgrade head` → `uv run python -m scripts.seed_templates`。
  - API：`uv run uvicorn app.main:app --port 8000`；worker：`uv run python -m app.workers`（兩個都要開）。
  - 前端：`cd frontend && npm run dev`（http://127.0.0.1:5173）。
  - 本機 LLM（M4）：這台開發機的 `C:\Users\y7632\.ollama` 是指向不存在路徑的連結，`ollama serve` 要用 `USERPROFILE=C:\howder-wt\ollama-home OLLAMA_MODELS=D:\ollama\models` 啟動；模型 `qwen3:8b`、`qwen3:14b`。換電腦的話照 Ollama 一般安裝即可。
- **完成前檢查**（CLAUDE.md 第 11 節）：後端 `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest`；前端 `npm run typecheck && npm run lint && npm run test && npm run build`；有畫面改動就在瀏覽器看 375px 與 1280px。
  - 目前 `mypy` 已知 1 個錯（`api/v1/campaigns.py:322`），不是你造成的，見「開發中發現」。

### 建議順序與分工
| 順序 | 任務 | 誰 | 備註 |
|---|---|---|---|
| 1 | M2-23 介面拿掉「模型」用語 | 開發者 | 小、獨立，適合先熟悉專案 |
| 1 | M2-17 每天最晚寄送時間 | 開發者 | 獨立 |
| 1 | 「開發中發現」的小修（mypy、焦點、防呆文字） | 開發者 | 每項一個 commit |
| 2 | M2-19 ADR 0007 個人帳號 | 開發者查資料＋負責人決定 | 要負責人用寄件帳號登入 Azure 入口網站註冊應用程式 |
| 3 | M2-20 登入支援個人帳號 → M2-21 連結 Outlook | 開發者 | 依 M2-19 的結論 |
| 4 | M2-15 真實寄信驗收 | 負責人＋開發者 | 負責人自己登入、授權；開發者在旁操作系統 |
| — | M4-06b 業務盲評 | 業務 | 開發者先準備 10 封草稿 |
| — | M4-06g CLAUDE.md 指令補充 | 開發者 | 改 CLAUDE.md 前先問負責人 |
| — | M4-06l 完整 sandbox 50 封驗收 | 開發者 | 需要本機 Ollama |
| — | M1-03 Docker 驗證 | 有 Docker 的電腦 | 這台的 Docker Desktop 起不來 |
| 之後 | M5 | 先拆細 | CLAUDE.md 第 13 節：開始前拆成和 M1 一樣細 |

### M2-23 介面拿掉「模型」用語
- **為什麼**：系統沒有模型，名單是在系統外整理好的 Excel／CSV（CLAUDE.md 開頭、名詞表「匯入批次」）。
- **要改的地方**（行號是 2026-11-18 的，改之前再 grep `模型\|MLE` 確認）：
  - `frontend/src/pages/AdminImportsPage.tsx`：第 40 行提示「模型版本 run #」→「匯入批次 #」；第 141、158 行表頭與 `data-label`「模型版本」→「匯入批次」；第 212、215 行「MLE 提供」的漏斗區塊標題（這一塊要不要整個拿掉見「開發中發現」的漏斗項目，先只改字）。
  - `frontend/src/pages/recommendations/CompanyDetailPanel.tsx`：第 95 行「模型版本 run #」→「匯入批次 #」；第 147 行「模型沒有提供理由」→「匯入資料沒有提供推薦理由」；第 213 行「模型原判」→「匯入時的產業」。
  - `frontend/src/pages/recommendations/ReviewWorkspace.tsx` 第 156 行：「模型沒有提供推薦理由…」→「匯入資料沒有提供推薦理由…」。
  - `frontend/src/pages/recommendations/RejectDialog.tsx` 第 58 行：「這會用來改善推薦模型。」→「原因會列入名單品質報表。」
  - `frontend/src/pages/performance/AdminModelPage.tsx` 第 31 行標籤「匯入批次（模型版本）」→「匯入批次」，第 10 行註解；**同時改** `Performance.test.tsx` 第 118 行用到的標籤文字。
  - 註解：`components/Stars.tsx` 第 7、11 行、`lib/labels.ts` 第 229 行、`recommendations/AddCompanyDialog.tsx` 第 15 行，「MLE／模型」改成「整理好的名單」。
  - **不要改**：`api/errorMessages.ts` 的 `LLM_*` 訊息（那裡的「模型」指 AI 寫信的 LLM，是對的）；`Campaigns.test.tsx` 的 AI 模型與 prompt 版本；資料庫與 API 欄位名稱 `model_run`、`run_id`、`model_name`、路由 `/admin/model`。
- **驗收**：`grep -rn "模型\|MLE" frontend/src` 只剩 LLM 相關；前端四項檢查通過；瀏覽器看匯入頁、公司側欄、審核畫面、排除對話框、名單品質頁（375px／1280px）。
- **Commit**：`style:` 或 `refactor:`（純文字），進度更新放同一個 commit。

### M2-17 每天最晚寄送時間 `SEND_DAY_END_HOUR`（F-MAIL-6、SPEC 7.5）
- **現況**：`backend/app/domain/send_limits.py` 的 `plan_send_times()` 只管每日上限（超過排到隔天 `day_start_hour`）和每分鐘限速；沒有「幾點以後不寄」。呼叫的地方：`backend/app/services/send_service.py` 第 127～133 行（按寄出時排時間）、第 193 行（worker 寄出前發現今天已滿 → `jobs.Reschedule` 到隔天）。
- **步驟**：
  1. `backend/app/config.py` 加 `send_day_end_hour: int = 18`；在 `_guard_production` 檢查 `0 <= send_day_start_hour < send_day_end_hour <= 24`，不合法啟動失敗。`.env.example` 加說明（台灣時間）。
  2. `plan_send_times()` 加參數 `day_end_hour: int = 24`：排到的時間（當地時間）`>= day_end_hour` 點就跳到隔天 `day_start_hour`，並重新計數。
  3. 一併處理「早於上班時間」：排到的時間早於當天 `day_start_hour` 就延到當天 `day_start_hour`。**這會改變現在的行為**（目前半夜按寄出會立刻寄），先跟負責人確認；確認後 SPEC 7.5 寫清楚。注意之前 sandbox 示範是用 `SEND_DAY_START_HOUR=0` 繞過，之後示範要再加 `SEND_DAY_END_HOUR=24`。
  4. `send_service.py` 兩個地方都帶入設定；worker 寄出前如果現在已超過 `send_day_end_hour`（例如 job 延遲），也 `Reschedule` 到隔天上班時間。
- **測試**（名稱帶 `test_f_mail_6_`）：`tests/test_mail_domain.py` 加單元測試——17:59 照排、18:00 跳隔天 9:00、跨日同時碰到每日上限、早於 9 點延到 9 點、台灣時區跨 UTC 日；設定不合法時啟動失敗；worker 超過時間會改期（可參考 `tests/test_campaigns.py` 寄出相關測試的寫法）。
- **文件**：SPEC 7.5、`.env.example`、CLAUDE.md 不用改。

### M2-19 ADR 0007：先用個人 Microsoft 帳號登入與寄信
- **背景**：公司 Microsoft 365 帳號之後再說（SPEC 11-4）。先用一個專門測試用的個人 outlook.com 帳號當寄件人，寄到負責人自己的信箱（實際地址只寫在 `.env` 的 `MAIL_ALLOWED_RECIPIENTS`，已設定好）。系統不會、也不可以用信箱密碼；寄件帳號的擁有人要自己在 Microsoft 頁面登入、按同意。
- **現在的設計**（ADR 0005）：前端用 MSAL 登入公司租用戶，拿 `api://{clientId}/access_as_user` 的 token 給後端；後端用 On-Behalf-Of（`backend/app/services/mail_token.py` 的 `MsalOboClient`）換成 Graph `Mail.Send` token，MSAL 快取用 Fernet 加密存在 `user_mail_credential.token_cache`；worker 用 `acquire_silent` 拿 token 寄信。
- **要查清楚的事**（查 Microsoft identity platform 官方文件，結論與連結寫進 ADR）：
  1. 個人帳號能不能在 Azure 入口網站註冊應用程式（可能要先有預設目錄或免費 Azure 帳號）；「支援的帳戶類型」選「僅個人 Microsoft 帳戶」（`consumers`）還是「組織目錄與個人帳戶」（`common`，之後切公司帳號比較方便）。
  2. 個人帳號拿「自己 API」（`api://…/access_as_user`）的 access token 有沒有限制（例如應用程式資訊清單要設 `accessTokenAcceptedVersion: 2`）；token 的 issuer 是個人帳號固定的租用戶 ID，要確認實際值。
  3. On-Behalf-Of 能不能用在個人帳號；**不能的話**，「連結 Outlook」改成後端的授權碼流程（PKCE＋機密用戶端，scopes `Mail.Send`、`User.Read`、`offline_access`），refresh token 照舊用 Fernet 加密存在 `user_mail_credential`，worker 不用改。
  4. 個人帳號用 Graph `POST /me/sendMail` 寄信的限制（每日上限、新帳號可能被限制寄送或要求驗證）。
- **要決定**（寫成 ADR 的「決定」，給負責人確認）：登入與連結各用哪種流程；設定怎麼做成可切換（建議新增 `ENTRA_AUTHORITY`：`consumers`／`common`／`organizations`／租用戶 ID，預設維持公司租用戶），之後換公司帳號只改 `.env`。
- **需要負責人做的事**：用寄件測試帳號登入 Azure 入口網站 → 註冊應用程式 → 設定重新導向 URI（開發用 `http://localhost:5173` 與後端 callback，依 ADR 決定）→ 建立 client secret 並**自己**填進 `backend/.env` 的 `ENTRA_CLIENT_SECRET`；`MAIL_TOKEN_KEY` 用 `.env.example` 裡的指令產生後自己填。client ID、租用戶 ID 不是機密，可以告訴開發者。
- **產出**：`docs/adr/0007-personal-microsoft-account.md`（背景、決定、理由，100 行以內）；SPEC 7.x 寄信流程與 11-4 更新；依結論把 M2-20、M2-21 再修細。這個任務只寫文件，不寫程式。

### M2-20 登入支援個人 Microsoft 帳號（依 M2-19）
- **要改的地方**：
  - `backend/app/services/auth.py`：第 28～29 行 JWKS 網址與第 41 行 issuer 都用 `settings.entra_tenant_id` 組；改成依 M2-19 的 `ENTRA_AUTHORITY` 決定 JWKS 網址，issuer 檢查改成「允許的 issuer 清單」（不可以關掉 issuer 驗證）。audience 第 40 行維持 client id 與 `api://{client id}`。
  - 確認個人帳號 token 裡哪個 claim 有 email（`preferred_username`／`email`），對應到 `app_user` 的邏輯跟著調整；負責人的帳號要當管理員就把它寫進 `.env` 的 `BOOTSTRAP_ADMIN_EMAILS`（不 commit）。
  - `backend/app/config.py`、`backend/.env.example`：新設定與說明。
  - `frontend/src/auth/msal.ts` 第 20 行 `authority`：改成讀 `VITE_ENTRA_AUTHORITY`（沒設時沿用租用戶 ID）；`frontend/.env.example` 加這一行。
- **測試**（名稱帶 `test_m2_20_`）：參考 `tests/test_auth.py` 用自己產生的金鑰簽假 token（`signing_key` 參數），測個人帳號 issuer 通過、別的租用戶被拒、audience 錯被拒、過期被拒；不連真實 Microsoft。
- **驗收**：負責人自己用寄件測試帳號在 http://127.0.0.1:5173 登入成功、看到推薦清單；後端 log 不印 token。

### M2-21 「連結 Outlook」支援個人帳號（依 M2-19）
- **現況**：`backend/app/api/v1/mail_connection.py`（`get_obo_client`、`get_cipher` 可在測試替換）、`backend/app/services/mail_token.py`（`OboClient` 介面、`connect`、`disconnect`、`access_token_for`）、前端 `frontend/src/pages/campaigns/MailConnectionBanner.tsx` 與 `api/endpoints.ts` 的 mail-connection 呼叫。
- **如果 M2-19 結論是授權碼流程**：
  1. `OboClient` 介面擴充或新增 `MailTokenProvider`（產生授權網址、用 code 換 token、`acquire_silent`），worker 用的 `access_token_for` 不改呼叫方式。
  2. 新 API：`GET /me/mail-connection/start` 回傳授權網址（帶 `state` 與 PKCE）；`GET /me/mail-connection/callback` 驗證 `state`（綁定目前登入的使用者、短時間過期，可用 `MAIL_TOKEN_KEY` 加密成 Fernet 字串，不必新增資料表）→ 換 token → 加密存進 `user_mail_credential` → 轉回前端頁面。需要資料表的話另開 migration、單獨 commit。
  3. 前端「連結 Outlook」改成導向授權網址；回來後顯示已連結；token 失效時狀態 `needs_reconnect`，橫幅提示重新連結（現有行為保留）。
- **安全**：`state` 不對就拒絕；回應、log、錯誤訊息都不可以出現 code、token、client secret；錯誤用 `{ "error": { "code", "message" } }`，新的 code 加進 `frontend/src/api/errorMessages.ts`。
- **測試**（名稱帶 `test_m2_21_`）：用假的 token 端點（`httpx.MockTransport` 或假的 provider）測——成功連結、`state` 錯誤或過期被拒、別人的 `state` 被拒、換 token 失敗、`needs_reconnect`、回應不含權杖；前端 Vitest 測橫幅按鈕。

### M2-15 驗收：用個人帳號真實寄 10 封（前置：M2-19～M2-21）
- **誰**：負責人自己登入寄件測試帳號、按同意；開發者操作系統。開發者不代填密碼、不代按同意。
- **`backend/.env`**（不 commit）：`ENV=development`、`AUTH_MODE=entra`、M2-19 決定的 `ENTRA_*` 設定、`ENTRA_CLIENT_SECRET` 與 `MAIL_TOKEN_KEY`（負責人自己填）、`MAIL_MODE=live`、`MAIL_ALLOWED_RECIPIENTS`（已設好，負責人自己的收件信箱）、`DAILY_SEND_LIMIT=10`、`SEND_PER_MINUTE=1`（已設好）。白名單是空的話系統不會啟動（M2-22）。
- **步驟**：
  1. 用全新的空資料庫：`HOWDER_PGDATA` 指到新的純英文資料夾啟動 `scripts.dev_db` → `alembic upgrade head` → `seed_templates`。
  2. 準備 10 家假公司的 CSV（格式照 `docs/samples/import_v1_sample.csv`，公司名用「測試」開頭的假名）；以管理員身分匯入並確認。
  3. 每家加一位聯絡人，email 都填白名單裡的收件信箱（只存在這個測試資料庫，不寫進任何檔案）；另外加 1 家聯絡人用 `blocked@example.com`，用來確認白名單會擋。
  4. 業務頁審核通過 → 建立批次（模板）→ 預覽、核准 10 封 → 「連結 Outlook」（負責人登入授權）→ 寄出。`blocked@example.com` 那家應該在建立批次時就被排除，原因「收件者不在測試白名單」。
  5. 確認：收件信箱收到 10 封；寄件帳號的「寄件備份」有 10 封；`email_message` 有 10 筆；每封結尾有退訂說明；14 天內再寄同一家會被擋。
  6. 結束後 `MAIL_MODE` 改回 `sandbox`；結果（不含信箱地址）寫進 CHANGELOG，打勾 M2-15。
- **注意**：新的個人帳號可能被 Microsoft 限制寄送量或要求驗證；遇到就記錄錯誤代碼，不要調高上限硬寄。

### M4-06g 本機冒煙腳本：剩 CLAUDE.md 指令補充
- 腳本 `backend/scripts/llm_smoke.py` 已完成並實測通過；只剩把下面幾行加進 CLAUDE.md 第 3 節指令區。**改 CLAUDE.md 前先問負責人**：
  - `ollama serve`（這台機器要用上面「開發環境」那段的環境變數啟動）
  - `uv run python -m scripts.llm_smoke [--mode full_ai] [--model qwen3:14b --runs 3]`
  - `uv run python -m scripts.llm_bench --n 50 --concurrency 2`
- 負責人同意、改完後打勾 M4-06g 與上層 M4-06（如果 b、l 也完成）。

### M4-06b 選地端模型：剩業務盲評
- 速度與失敗率已實測（ADR 0006）：`qwen3:8b` 每封約 3 秒，`qwen3:14b` 約 28 秒。
- **開發者準備**：sandbox 用 10 家假公司（只用公司名、產業、推薦理由）各用 8b、14b 產生一封 `template_ai`，匯出成不標示模型的對照表（A／B 隨機），對應表另外保存。
- **業務做**：每封評 1～5 分——通順度、內容正確、有沒有捏造（實績／價格／認證／交期）、要改多少。
- **結果**：平均分數、捏造次數寫回 `docs/adr/0006-local-llm-first.md`，決定預設模型（`LOCAL_LLM_MODEL`）。

### M4-06l 完整 sandbox 50 封驗收
- LLM 階段已測過（`qwen3:8b` 50 封 82 秒、0 失敗）。還要走完整流程：`MAIL_MODE=sandbox`、開本機 Ollama、API 與 worker → 準備 50 家假公司 → 建立 `template_ai` 批次 → 從按下建立到 50 封都出現在預覽佇列計時 → 記錄總耗時與失敗數，對照 F-MAIL-3「50 封 3 分鐘」→ 寫進 ADR 0006 → 打勾。

### M1-03 Docker 驗證
- 需要一台 Docker Desktop 能啟動的電腦：在專案根目錄 `docker compose up -d` → 把 `DATABASE_URL` 指到 compose 的 Postgres → `alembic upgrade head` → `uv run pytest` 與 API 都正常 → 打勾。發現 compose 檔要改就一起修。

### M5 延伸（開始前要先拆細）
- CLAUDE.md 第 13 節：開始 M5 前先拆成和 M1 一樣細的任務（一個任務一個 commit 做得完），拆好加在 M5 底下，編號用 `M5-01a`、`M5-01b`…。
- M5-01 來源管理 `/admin/sources`（SPEC F-SRC-1）：列出資料來源、新增、停用、各來源撈取筆數與回覆率、依日期區間篩選新增的公司。預計要：來源維度表 migration、API、管理頁、回覆率讀 view（KPI 只定義在 view）。
- M5-02 產品標籤維護 `/admin/tags`（SPEC F-TAG-1）：標籤內容要等厚達提供「產品用在哪裡」；標籤命中數與回覆率讀 view。
- M5-03 專用信箱轉寄、自動比對案件（SPEC F-TRK-1）：系統不讀業務個人信箱（ADR 0004）；需要專用信箱與 Graph 讀信權限，先寫 ADR；比對結果只產生「待確認的回填」，業務確認後才生效。
- M5-04 管理者 BI 儀表板（案件數、成功開案數）：先跟負責人確認要哪些數字、用內建頁面還是外部 BI 工具。

### 「開發中發現」的處理方式
- **可以直接做的小修**（每項一個 `fix:` commit，先寫重現測試再修，CLAUDE.md 第 9 節第 3 點）：
  - mypy 錯誤：`backend/app/api/v1/campaigns.py` 第 322 行 `row.count` 被 mypy 當成 Row 的方法 → 改成 `row[1]` 或在查詢裡替欄位取別名；`uv run mypy app` 要變成 0 個錯。
  - 防呆文字固定寫「14 天內已經寄過」：改成依 `RECENT_SEND_DAYS` 顯示天數（文字由後端 `/campaigns/exclusion-reasons` 提供，在 `backend/app/domain/send_guard.py` 的原因標籤）。
  - 公司詳情側欄打開時焦點落在「排除…」→ 改落在標題或關閉鈕；受控對話框關閉後焦點回到原本的按鈕（`Modal` 元件還原焦點）。鍵盤實測。
  - `AdminImportsPage` 元件測試（Vitest）：上傳預覽、確認匯入、錯誤列表四種狀態。
  - 前端 bundle 超過 500 kB：dev 模式不載入 MSAL（動態 import）或依路由切分。
  - 手機版篩選列太長（14 個欄位）：收合成「篩選」按鈕，用 Radix 的對話框或側欄。
- **要負責人決定的**（決定後才做，不做就照 CLAUDE.md 第 13 節直接刪掉並記在 CHANGELOG）：漏斗數字要不要移除、`gold_label` 表要不要刪（要新增 migration）、寄信時要不要自動認領（SPEC 11-11）、案件聯絡人退訂後要不要自動換人、Excel 缺統編找整理的人補、總覽門檻「只定義一次」要不要改成 SQL 函式。

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
- [x] M1-12 Microsoft Entra ID OIDC 登入（後端驗證 token） — 2026-11-17（後端驗證完成；尚未用真實帳號測試。2026-11-18 起先用個人帳號，見 M2-20）
- [x] M1-13 `GET /api/v1/me` 與 `app_user` 自動建立 — 2026-11-17
- [x] M1-14 角色權限檢查（sales / manager / admin）＋測試：業務不能呼叫 `/admin` — 2026-11-17
- [x] M1-15 前端登入流程與路由守衛 — 2026-11-17（dev 快速登入已驗證；Entra 登入流程已寫好，尚未用真實帳號測試，見 M2-20）

### 名單匯入（F-IMP）
- [x] M1-16 `importer`：解析 CSV/XLSX，支援 UTF-8 / Big5（F-IMP-1） — 2026-11-17
- [x] M1-17 `importer`：欄位驗證（統編 8 碼、產業/優先級要在維度表裡）（F-IMP-4） — 2026-11-17
- [x] M1-18 `importer`：產生預覽差異（新增 / 更新 / 錯誤）（F-IMP-2） — 2026-11-17
- [x] M1-19 `importer`：確認寫入，以統編去重，建立 `model_run` 與 `classification`（F-IMP-3） — 2026-11-17
- [x] M1-20 Excel 欄位轉換規則（拆「明確但競合」、忽略圖例欄）（SPEC 8.3） — 2026-11-17
- [x] M1-21 `POST /imports`、`POST /imports/{id}/commit` API（F-IMP-2、F-IMP-5） — 2026-11-17（F-IMP-5 API 匯入 2026-11-18 移除）
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
  - [x] M2-01a 後端 `POST /contacts`、`PATCH /contacts/{id}`、標記退訂、個資刪除（真的刪除，連帶刪除郵件內容並寫 `activity_log`）。來源必填、email 格式檢查、同一家公司不重複（SPEC 9 個資） — 2026-11-17（migration 0004 來源 CHECK；退訂同時把公司改成 `do_not_contact`，2026-11-18 M3-17 改成只標記聯絡人；刪除限主管／管理員且要填原因）
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
- [ ] M2-15 驗收：用個人 Microsoft 帳號（outlook.com）真實寄 10 封到使用者自己的另一個信箱，確認出現在寄件備份；用全新的空資料庫、只放測試公司，白名單只放那個信箱、每天上限 2～10 封（前置：M2-19～M2-21，M2-22 已完成；公司帳號之後再測）

### 2026-11-18 使用者決定後追加
- [x] M2-16 批次「待寄出」狀態（F-MAIL-4）：migration 讓 `campaign.status` CHECK 加上 `ready`（單獨 commit）；草稿都處理完、還沒按寄出時改成 `ready`，按寄出後 `scheduled`；前端狀態文字＋測試 — 2026-11-18（migration 0011；「我的待辦」也算待寄出的批次；既有批次要等下一次草稿動作才會重算狀態）
- [ ] M2-17 每天最晚寄送時間 `SEND_DAY_END_HOUR`（預設 18，台灣時間；F-MAIL-6）：超過的排到隔天 `SEND_DAY_START_HOUR`；設定、`.env.example`、`domain/send_limits` 單元測試
- [x] M2-18 測試收件者白名單 `MAIL_ALLOWED_RECIPIENTS`（M2-15 真實寄信前的安全機制）：`domain/send_guard` 加 `RECIPIENT_NOT_ALLOWED`，建立草稿、按寄出、worker 寄出前都檢查；順便修正建立批次時沒讀 `RECENT_SEND_DAYS` — 2026-11-18
- [ ] M2-19 ADR 0007：先用個人 Microsoft 帳號（outlook.com）登入與寄信。要先查清楚並請使用者決定：
  - 個人帳號能不能直接註冊應用程式（可能需要先有一個 Entra 目錄），應用程式要設成支援個人帳號（`consumers` 或 `common`）
  - ADR 0005 的 On-Behalf-Of 查不到支援個人帳號的官方說明 → 「連結 Outlook」可能改成授權碼流程（PKCE＋機密用戶端，refresh token 一樣用 Fernet 加密）
  - 公司帳號之後要能用設定切回，不重寫流程
- [ ] M2-20 登入支援個人 Microsoft 帳號（依 M2-19）：authority、token 的 issuer／audience 驗證、前端 MSAL 設定；用假 token 測試
- [ ] M2-21 「連結 Outlook」支援個人帳號（依 M2-19）：開始連結、Microsoft 轉回的 callback、加密保存、失效時 `needs_reconnect`；用假的 Microsoft 端點測試，回應與 log 不含權杖
- [x] M2-22 真實寄信的安全條件：開發環境 `MAIL_MODE=live` 時 `MAIL_ALLOWED_RECIPIENTS` 不能是空的才可啟動，`ENV=test` 一律不行，正式環境不受影響；CLAUDE.md 第 6 節第 3 點已依使用者同意改寫 — 2026-11-18（真實寄信時用全新的空資料庫、只放測試公司，記在 M2-15 驗收步驟）
- [ ] M2-23 介面拿掉「模型」用語（2026-11-18：沒有模型，名單是整理好的 Excel）：匯入頁的「模型名稱」欄位與「模型版本 run #」改成「匯入批次 #」；公司詳情的「模型版本」「模型原判」「模型沒有提供理由」改成「匯入資料」的說法；排除對話框「改善推薦模型」改成「名單品質報表」；資料庫欄位名稱（`model_run`、`run_id`）不改

## M3 案件追蹤與總覽（閉環）

依 2026-11-17 會議調整（ADR 0004）：先做出「寄信 → 人工回填 → 成交」的閉環，AI 寫信移到 M4。
完成條件（SPEC 10）：用 100 筆名單寄出後，模擬一位客戶回覆並回填到成交，總覽頁的回覆率、成交數、待辦提醒都正確。
2026-11-18 已依 CLAUDE.md 第 13 節拆成一個 commit 做得完的大小。建議順序：先做閉環（M3-07～M3-12、M3-04），再做 CSV v1 與名單功能（M3-06、M3-13），最後 M3-14 示範、M3-15 檢查。

- [x] M3-04 退訂處理：客戶用任何管道要求時，業務手動標記（F-CASE-5、F-TRK-3；拆成下列 a） — 2026-11-18
  - [x] M3-04a 案件頁「客戶要求退訂」：標記聯絡人退訂、公司改 `do_not_contact`、案件結案（結果 `lost`，備註「退訂」），時間軸留紀錄＋測試 — 2026-11-18（聯絡人退訂也會一併結案；同日 M3-17 改成公司還有其他聯絡人時只標記聯絡人、案件照常）
- [x] M3-06 CSV 欄位規格 v1（SPEC 8.4） — 2026-11-18
  - [x] M3-06a migration 0009：`company` 加 `country`、`url_status`、`source`；`classification` 加 `fit_stars`、`product_type`、`tags`；匯入批次存漏斗前段數字（單獨 commit） — 2026-11-18
  - [x] M3-06b 匯入器支援新欄位、`invalid` 網址列為「略過」、未知欄位提示；附一份範例 CSV（假資料）給 MLE — 2026-11-18（範例在 `docs/samples/import_v1_sample.csv`；舊版 Excel 沒有來源欄照樣匯入並提示；API 匯入可帶 `funnel`）
  - [x] M3-06c 推薦清單顯示小數星等，新增篩選條件：國別、來源、網址狀態、產品類型、標籤、星等下限（F-REC-1、F-REC-7） — 2026-11-18
- [x] M3-07 migration：`opportunity` 改名擴充為 `sales_case`，新增 `case_update`（拆成下列 a） — 2026-11-18
  - [x] M3-07a migration 0006（單獨 commit）： — 2026-11-18
    - `opportunity` 沒有資料也沒有程式在用，直接改建成 `sales_case`：編號 `case_no`（C-0001）、公司、聯絡人、負責業務、來源（`email`／`tracking`）、狀態、寄出日、最後回填時間、下次追蹤日、成交金額、結案時間
    - 同一家公司同時只能有一件未結案的案件（部分唯一索引）
    - `case_update`：管道（email／line／wechat／phone／visit／other／system）、聯絡人、結果（replied／negotiating／won／lost／no_response／sent）、備註、下次追蹤日、金額
    - ORM、`schema.sql`、SPEC 8.1 同步
- [x] M3-08 `domain` 案件規則：狀態轉換、回填帶動公司狀態、逾期判斷（7 天、下次追蹤日、14 天）＋單元測試（拆成下列 a） — 2026-11-18
  - [x] M3-08a `domain/case_rules.py`： — 2026-11-18（待辦條件放在 view，domain 只放天數與「標成無回應」判斷）
    - 案件狀態機（sent／tracking → replied → negotiating → won／lost；無回應 `no_response` 可以再回填）
    - 回填結果對應公司狀態，跳級時依序走過中間狀態（例如 sent 直接回填成交 → replied → meeting → won）
    - 「加入追蹤」的公司是 `approved`，公司狀態機加上 `approved → replied／lost`（SPEC 3.1 同步）
    - 待辦判斷：寄出 7 天沒有回填、超過下次追蹤日、寄出 14 天沒回覆
- [x] M3-09 案件 API：寄出時自動開案（F-CASE-1）、`POST /cases` 加入追蹤（F-REC-9）、`POST /cases/{id}/updates` 回填（F-CASE-2）、列表與詳情（拆成下列 a、b） — 2026-11-18
  - [x] M3-09a `services/case_service`：worker 寄出成功時開案（已有未結案案件就在時間軸加一筆「寄出」）；`POST /cases` 批次加入追蹤（整批檢查權限與鎖定）＋測試 — 2026-11-18
  - [x] M3-09b `GET /cases`（狀態、負責業務、寄信日、只看逾期；各狀態件數）、`GET /cases/{id}`（時間軸）、`POST /cases/{id}/updates` 回填（帶動公司狀態、寫 `activity_log`）、`GET /cases/export` CSV＋權限測試（業務只看自己的） — 2026-11-18（和 M3-09a 同一個 commit：API 與 service 一起測）
- [x] M3-10 worker 每日催辦（`job` 排程）＋ `GET /reminders`（F-CASE-3；拆成下列 a、b） — 2026-11-18
  - [x] M3-10a migration 0007（單獨 commit）：view `v_case_reminder`（逾期未回報、該追蹤了、無回應建議拜訪），提醒條件只在 view 定義一次 — 2026-11-18
  - [x] M3-10b worker `case_daily`：每天把寄出 14 天沒回覆的案件標成 `no_response`（時間軸記一筆 system），做完排下一次；worker 啟動時確保有一筆排程；`GET /reminders`＋測試 — 2026-11-18（另外新增 migration 0008 讓 `job.kind` 接受 `case_daily`）
- [x] M3-11 前端 `/cases`：列表、各狀態件數、時間軸、回填表單；可以只用鍵盤回填（F-CASE-4；拆成下列 a、b） — 2026-11-18
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

### 2026-11-18 使用者決定後追加（M3-13 已完成，搜尋另開任務）
- [x] M3-16 建立批次頁（`/campaigns/new`）候選公司搜尋與篩選（公司名稱／統編、產業、星等），沿用推薦清單的篩選參數 — 2026-11-18（`GET /campaigns/candidates` 直接吃推薦清單的 `list_filters`；勾選的公司換篩選後仍保留，「全選」只動目前顯示的）
- [x] M3-17 退訂只標記該聯絡人（F-CASE-5 已改）：公司所有聯絡人都退訂，或標記時勾選「整家公司不再聯絡」，才改 `do_not_contact` 並結案；`domain/contact_rules` 規則＋單元測試；案件頁與聯絡人區塊加勾選框 — 2026-11-18（還有其他聯絡人時案件照常進行，不結案）
- [x] M3-18 取消退訂：`POST /contacts/{id}/resubscribe` 只限主管／管理員、必填原因、寫 `activity_log`；公司若因此恢復可聯絡，狀態怎麼退回要在 domain 定義並測試；前端入口在公司詳情聯絡人區塊 — 2026-11-18（公司若是 `do_not_contact` 就退回 `approved`，重新進入候選名單，先前寄信進度不帶回；規則在 `company_rules.status_after_resubscribe`）

## M4 AI 寫信、績效與名單品質（2026-11-18 拆細；沒有模型，名單是整理好的 Excel 匯入，不做任何回傳）

> **AI 先用本機能跑的環境**（2026-11-18 使用者決定）：Ollama 0.40（OpenAI 相容 API `http://127.0.0.1:11434/v1`，模型放在 `D:\ollama\models`），已下載 `qwen3:8b`、`qwen3:14b`；GPU 是 RTX 5060 Laptop 8 GB、RAM 24 GB。公司 GPU 主機（SPEC 11-10）確認後只改 `LOCAL_LLM_BASE_URL`、`LOCAL_LLM_MODEL`，不改程式。
> 自動化測試一律用 `FakeLlmClient` 或假的 HTTP 回應，不連本機 Ollama（CLAUDE.md 第 6 節第 4 點）；連本機模型只在手動腳本和驗收時做。
> 建議順序：M4-06（寫信）→ M4-08（官網摘要）→ M4-07（回覆態度）→ M4-02（名單品質）→ M4-01（績效頁）→ M4-09（檢查）。

### 原始任務（保留編號，細項在下面各小節）
- [x] M4-01 績效頁：漏斗、各星級成交率、各來源／標籤／模板回覆率、業務排行（F-TRK-5）→ 拆成 M4-01a～c — 2026-11-18
- [x] M4-02 排除原因報表（F-MLE-1，內部的名單品質報表）→ 拆成 M4-02a、b — 2026-11-18
- [ ] M4-06 prompt `invite_v1`＋`template_ai` / `full_ai` 生成（F-MAIL-2、F-MAIL-3；原 M3-01）。先用地端 LLM（ADR 0006）→ 拆成 M4-06a～l
- [x] M4-07 依回填內容判斷回覆態度（F-TRK-2；原 M3-03）→ 拆成 M4-07a～c — 2026-11-18
- [x] M4-08 官網摘要：給 AI 寫信用的公司背景（SPEC 7.4；M4-06 的前置）→ 拆成 M4-08a～e — 2026-11-18

### AI 寫信（M4-06；F-MAIL-2、F-MAIL-3、F-MAIL-8、SPEC 7.4、ADR 0006）
依這個順序做：a → e → f → g → h → c → i → j → k → b → d → l

- [x] M4-06a `LlmClient` 介面（輸入 system prompt＋使用者內容，回傳文字與耗時、token 數）＋`FakeLlmClient`；設定 `LLM_PROVIDER`（預設 `local`）、`LOCAL_LLM_BASE_URL`（預設本機 Ollama）、`LOCAL_LLM_MODEL`（預設 `qwen3:8b`）、`LLM_TIMEOUT_SECONDS`、`LLM_CONCURRENCY` 加進設定與 `.env.example`；依設定注入的測試（原本這一項也含 JSON 驗證、簡體字檢查、逾時重試，改拆到 M4-06e、M4-06f） — 2026-11-18
- [x] M4-06e `domain/ai_rules.py`（純函式）：去掉 qwen3 的 `<think>…</think>` 思考段、從回覆取出 JSON、驗證必要欄位與長度（主旨、`ai_paragraph`、`body_text`）、常見簡體字檢查；每條規則都有單元測試 — 2026-11-18
- [x] M4-06f `LocalLlmClient`：呼叫 `/v1/chat/completions`（要求 JSON 格式、關閉 qwen3 思考模式、溫度可設定、逾時）；連不上、逾時、HTTP 錯誤都轉成錯誤代碼（`LLM_UNAVAILABLE`、`LLM_TIMEOUT`…）；用假的 HTTP 回應測試，不連真實 Ollama — 2026-11-18
- [ ] M4-06g 本機冒煙腳本 `scripts/llm_smoke.py`：對本機 Ollama 用 1 家假公司跑一次，印出耗時、token 數、JSON 是否合格、有沒有簡體字（手動執行，不進 pytest）；`CLAUDE.md` 第 3 節指令補上 `ollama serve` 與這支腳本（改 CLAUDE.md 前先問使用者）（進行中：`backend/scripts/llm_smoke.py` 已完成並在 2026-11-18 對本機 Ollama `qwen3:8b` 實測通過——template_ai 與 full_ai 都 JSON 合格、無簡體字，冷啟動第一次約 62 秒、之後約 1.4 秒；實測發現 invite_v1 會把「寄件業務：」寫進署名，已新增 `invite_v2.md` 修正。`CLAUDE.md` 第 3 節指令補充尚未做，要先問使用者。啟動方式：這台機器的 `C:\Users\y7632\.ollama` 是指向不存在的 `D:\羊駝\.ollama` 的符號連結，`ollama serve` 要用 `USERPROFILE=C:\howder-wt\ollama-home OLLAMA_MODELS=D:\ollama\models` 另開 home 才起得來）
- [x] M4-06h migration：`email_draft` 加 `gen_provider`、`gen_model`、`prompt_version`（單獨 commit；同步 `db/schema.sql`、SPEC 8.1） — 2026-11-18（migration 0012）
- [x] M4-06c prompt `prompts/invite_v1.md`（system：厚達產品介紹先用佔位文字待 SPEC 11-5、不捏造實績／價格／認證／交期、繁體中文、只回 JSON）＋`template_ai`：AI 只寫 `{{ai_paragraph}}`，其他照模板代入；接進 worker `generate_drafts`，草稿記錄 provider、模型、prompt 版本（原本含 `full_ai`，改拆到 M4-06i） — 2026-11-18
- [x] M4-06i `full_ai`：AI 寫主旨＋整封內文，驗證長度，結尾一律由系統補上退訂說明（AI 寫的不算）；`ai_original` 存 AI 原稿供 F-MAIL-8 比對 — 2026-11-18
- [x] M4-06j 並發與失敗處理：依 `LLM_CONCURRENCY` 同時產生；JSON 不合格或有簡體字重試一次，再失敗就標 `failed` 並記錄錯誤代碼；「重新產生」走同一條路；錯誤代碼前端翻成中文 — 2026-11-18
- [x] M4-06k 前端：建立批次頁開放「模板＋AI 段落」「整封 AI 撰寫」（目前顯示「M4 開放」）；預覽佇列顯示這封是哪個模型、哪一版 prompt 產生的，AI 內容旁提醒業務核對事實 — 2026-11-18
- [ ] M4-06b 選地端模型：**先在本機比 `qwen3:8b` 與 `qwen3:14b`**（8 GB VRAM 放不下整個 14b，部分會跑在 CPU，要實測速度）；同一批 10 家公司（只用公司名、產業、推薦理由等公司層級資訊）各產生一封，業務盲評通順度、正確性、有沒有捏造、要改多少，記錄每封秒數與失敗率，結果寫回 ADR 0006。公司 GPU 主機到位後再加入其他候選模型重比（進行中：速度與失敗率已實測，結果寫進 ADR 0006——`qwen3:8b` 每封約 3 秒、`qwen3:14b` 約 28 秒；尚缺業務盲評通順度、正確性、有沒有捏造，這要業務來做）
- [x] M4-06d `ClaudeClient`（保留切換選項，用假的實作測試；要不要上線看 M4-06b 結果） — 2026-11-18（`ClaudeClient` 用 Messages API，假 HTTP 測試；`LLM_PROVIDER=claude` 需 `ANTHROPIC_API_KEY`，要不要上線由使用者決定）
- [ ] M4-06l 驗收（sandbox，不寄出）：本機 Ollama 用選定的模型產生 50 封 `template_ai` 草稿，記錄總耗時與失敗率，對照 F-MAIL-3「50 封 3 分鐘」；達不到就在 ADR 0006 記下本機實測數字，正式環境靠公司 GPU 主機（進行中：LLM 階段實測 `qwen3:8b` 50 封 `template_ai` 共 82 秒、0 失敗，達到 3 分鐘目標；尚未用完整 sandbox 流程〔建批次→worker→預覽〕跑 50 封）

### 官網摘要（M4-08；SPEC 7.4）
- [x] M4-08a migration：新增 `company_site_summary` 表（公司、抓取網址、摘要、抓取時間、狀態、錯誤代碼），`job.kind` 加上 `fetch_site`（單獨 commit；同步 `db/schema.sql`、SPEC 8.1） — 2026-11-18
- [x] M4-08b `services/site_fetcher.py`：只抓首頁和產品／關於我們頁；遵守 robots.txt，設定逾時與大小上限，同網域限速；HTML 轉純文字；測試用假的 HTTP 回應，不連真實網站 — 2026-11-18
- [x] M4-08c worker `fetch_site`：匯入確認後、或業務修正官網後排進佇列，不在匯入的 request 裡等；抓不到或沒有官網就標記失敗（錯誤代碼），寫信時改用推薦理由，不擋產生草稿 — 2026-11-18
- [x] M4-08d 摘要用本機 LLM 產生（prompt `prompts/site_summary_v1.md`，ADR 0006）；只留公司產品與產業描述，人名、email、電話用 domain 規則再過濾一次，不存進資料庫；單元測試 — 2026-11-18
- [x] M4-08e 寫信接上摘要（M4-06c 的輸入加官網摘要，沒有就用推薦理由）；公司側欄顯示摘要和抓取時間，業務可以按「重新抓取」 — 2026-11-18

### 回覆態度（M4-07；F-TRK-2）
- [x] M4-07a migration：`case_update` 加 `sentiment`（positive／neutral／negative，CHECK）與 `sentiment_source`（ai／manual），`job.kind` 加 `classify_reply`（單獨 commit） — 2026-11-18
- [x] M4-07b 回填有備註時排 worker `classify_reply`，用本機 LLM 判斷態度（prompt `prompts/reply_sentiment_v1.md`）；失敗不影響回填；`FakeLlmClient` 測試 — 2026-11-18
- [x] M4-07c 案件時間軸顯示態度標籤（附文字，不只靠顏色），業務可以手動修正並寫 `activity_log`；前端測試 — 2026-11-18

### 名單品質（M4-02；F-MLE-1，內部用，不回傳給 MLE）
- [x] M4-02a 排除原因 API：讀 `v_reject_reasons`，依匯入批次篩選（資料庫裡叫 `model_run`）；不在後端重算比例；權限：管理員、主管 — 2026-11-18
- [x] M4-02b `/admin/model` 頁「名單品質」：依批次切換排除原因分布；四種狀態；前端測試 — 2026-11-18

### 績效頁（M4-01；F-TRK-5）
- [x] M4-01a 績效 view：各星級回覆率／成交率、各資料來源與產品標籤回覆率、各模板回覆率、業務排行，都以 `v_case_fact` 為基礎（migration 單獨 commit；KPI 只定義在 view） — 2026-11-18
- [x] M4-01b API `GET /metrics/{funnel|win-rate|templates|reps}`：業務只看自己的，主管可看全團隊；日期與篩選同總覽 — 2026-11-18
- [x] M4-01c `/performance` 頁：表格為主、比例附件數、樣本不足標示；四種狀態；前端測試 — 2026-11-18

### 收尾
- [x] M4-09 M4 各頁 375px／1280px 瀏覽器檢查、鍵盤操作檢查（審核、核准都能只用鍵盤完成） — 2026-11-18（績效、名單品質、建立批次、公司側欄官網摘要、案件態度：375px 無橫向捲軸、1280px 正常，用隔離資料庫與假資料檢查；新增的控制項都是原生按鈕與選單，鍵盤可操作；1280px 只實際看過績效頁，其餘頁面 1280px 沿用既有版型，未逐頁截圖）

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
- [ ] 原始 Excel 第 44 列缺統編，匯入時會被略過；請整理 Excel 的人補上
- [ ] 公司詳情側欄打開時焦點落在「排除…」按鈕，改成落在標題或關閉鈕比較安全
- [ ] `RecommendationsPage` 與 `AdminImportsPage` 尚無元件測試（目前靠瀏覽器檢查）（進行中：已完成 RecommendationsPage 的加入追蹤與小數星等測試，AdminImportsPage 還沒有）
- [ ] 寄信不會自動認領公司（`owner_id` 留空，只有「認領」或「加入追蹤」才會），寄出後其他業務 14 天後仍可寄；要不要寄出時自動認領，請業務主管決定（M3-14 發現）
- [ ] 欄位自選等受控對話框關閉後，焦點回到頁面最上面而不是原本的按鈕；`Modal` 元件可加上關閉後還原焦點
- [ ] 推薦清單篩選列 M3-06c 後變成 14 個欄位，手機上更長；和上面「收合成篩選按鈕」一起處理
- [ ] `uv run mypy app` 在 `api/v1/campaigns.py`（目前第 322 行）報 1 個錯（`row.count` 被當成 Row 的方法），M3-17 之前就存在；改成 `row[1]` 或替欄位取別名即可
- [ ] 案件的聯絡人退訂、但公司還有其他聯絡人時，案件的 `contact_id` 仍指向已退訂的人；之後回填或再寄信要手動選其他聯絡人，可考慮自動換成下一位
- [ ] 匯入批次的漏斗數字（`import_batch.funnel`、總覽 `mle_funnel`、匯入頁的漏斗區塊）只有已移除的 API 匯入會寫入，之後不會有新資料；要不要移除請使用者決定
- [ ] 資料庫還留著沒在用的 `gold_label` 表（盲標已取消）；要刪得新增 migration，請使用者決定
- [ ] 建立批次時最近寄過的天數改讀設定後，防呆中文仍固定寫「14 天內已經寄過」，`RECENT_SEND_DAYS` 改值時文字不會跟著變
- [ ] 總覽的比例（回覆率、留存率）在 `metrics_service` 依篩選加總後計算，「寄出未滿 10 件不算」的門檻同時寫在 `v_kpi_summary` 和 `metrics_service.MIN_SAMPLE`；若要只定義一次，可改成 SQL 函式
