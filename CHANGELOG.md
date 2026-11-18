# 開發日誌

> 每結束一個開發階段（或一次對話）就在**最上面**新增一則。開新對話時，先讀最上面一則和 `PROGRESS.md`，就能接上進度。
> 格式固定五段：改了哪些檔案、解決了什麼問題、做了哪些決定、還沒處理的問題、下一步。

---

## 2026-11-18｜M4：AI 寫信、官網摘要、回覆態度、績效與名單品質

**改了哪些檔案**
- `backend/app/domain/ai_rules.py`、`site_rules.py`：AI 回覆檢查（去 `<think>`、取 JSON、長度、簡體字、態度、摘要）；官網文字轉換、連結挑選、公開位址檢查、個資過濾（純函式）
- `backend/app/services/llm.py`、`ai_writer.py`、`generator.py`：`LlmClient`（本機 Ollama／Claude／Fake）、prompt 載入與重試、`template_ai`／`full_ai` 產生與並發
- `backend/app/prompts/`：`invite_v1`（保留）、`invite_v2`（署名修正）、`reply_sentiment_v1`、`site_summary_v1`
- `backend/app/services/site_fetcher.py`、`site_service.py`、`sentiment_service.py`、`perf_service.py`；`api/v1/performance.py`、`cases.py`、`companies.py`、`campaigns.py`
- `backend/migrations/0012`～`0015`：草稿產生資訊、績效與排除原因 view、回覆態度、官網摘要表（各自單獨 commit；`db/schema.sql`、SPEC 已同步）
- `backend/scripts/llm_smoke.py`、`llm_bench.py`：本機 LLM 冒煙與速度實測（手動，不進 pytest）
- 前端：`/performance`、`/admin/model`、建立批次開放 AI 模式、預覽顯示模型與提示詞版本、公司側欄官網摘要、案件時間軸態度
- `docs/adr/0006-local-llm-first.md`：實測結果與暫定結論；`PROGRESS.md`、`docs/SPEC.md`

**解決了什麼問題**
- 業務可以選「模板＋AI 段落」或「整封 AI 撰寫」，AI 草稿一樣要預覽核准、系統結尾補退訂說明，不會自動寄出。
- 本機 `qwen3:8b` 50 封 `template_ai` 約 82 秒、0 失敗（達到 3 分鐘目標）；`qwen3:14b` 約 28 秒／封，在 8 GB VRAM 上達不到。
- 有官網的公司匯入後會在背景抓官網並摘要（遵守 robots.txt、限速、只抓公開位址、過濾個資），給 AI 寫信用；抓不到就改用推薦理由。
- 回填有備註時用本機 LLM 判斷客戶態度，業務可手動修正（手動優先，寫 `activity_log`）。
- 績效頁（星級、來源、標籤、模板、業務）與名單品質頁（各批次排除原因）上線；數字只從 view 來。

**做了哪些決定**
- 自動化測試一律不連 LLM 與網站：`ENV=test` 時 `get_llm_client`、`build_fetcher` 直接拒絕，測試要自己注入假的。
- prompt 只新增版本不覆蓋：實測發現 `invite_v1` 署名多出「寄件業務：」，新增 `invite_v2`。
- 官網摘要與回覆態度的失敗都不影響主流程（只記錄錯誤代碼）。
- 暫定用 `qwen3:8b`；是否改 14b 或啟用 Claude 等業務盲評與公司 GPU 主機到位後再決定。
- 順手修了一個既有測試的不穩：`test_f_case_2_update_moves_company_through_states` 讀 `activity_log` 沒有排序，偶爾失敗，補上 `ORDER BY`。

**還沒處理的問題**
- M4-06b：業務盲評（通順度、正確性、有沒有捏造、要改多少）還沒做，要業務參與。
- M4-06g：`CLAUDE.md` 第 3 節還沒補 `ollama serve` 與冒煙腳本指令（要先問使用者）。
- M4-06l：只量了 LLM 階段；用真實 sandbox 流程（建批次→worker→預覽）產生 50 封的完整驗收還沒跑。
- 這台機器的 `C:\Users\y7632\.ollama` 是指向不存在的 `D:\羊駝\.ollama` 的符號連結，`ollama serve` 要另開 home 才起得來（我沒有動你的連結）。
- `uv run mypy app` 仍有 1 個既有錯誤（`api/v1/campaigns.py`，與 M4 無關）。
- 官網摘要的人名過濾只用「職稱＋姓名」規則與 prompt 要求，無法保證抓到所有人名；之後可考慮加強或人工抽查。
- 績效頁的 1280px 只實際看過一頁；篩選目前只有日期區間，沒有產業等其他條件。

**下一步**
- M2-17；M4-06b／g／l（見上）；之後 M5（`PROGRESS.md`）。

---

## 2026-11-18｜範例 CSV 加 UTF-8 BOM；名單管理移除進階設定

**改了哪些檔案**
- `docs/samples/import_v1_sample.csv`：開頭加 UTF-8 BOM（Excel 雙擊開啟時中文會亂碼，是因為沒有 BOM）
- `backend/tests/test_import_v1.py`：新增 `test_m3_06b_sample_csv_has_utf8_bom`，防止之後又被存成沒有 BOM
- `docs/SPEC.md`：8.4 註明範例檔帶 BOM、MLE 另存請選「CSV UTF-8」
- `frontend/src/pages/AdminImportsPage.tsx`、`Page.module.css`：移除名單管理上傳表單的「進階設定」（模型名稱欄位）；後端 `model_name` 參數保留，選填

**解決了什麼問題**
- 範例 CSV 在 Excel 裡中文顯示不完整／亂碼。匯入器本來就讀得懂 UTF-8 與 UTF-8 BOM，不受影響。

**做了哪些決定**
- 修範例檔本身，不改匯入器。

**還沒處理的問題**
- MLE 自己產出的 CSV 若不是 UTF-8 或 Big5，仍會被拒絕並提示編碼錯誤。

**下一步**
- M2-17（`PROGRESS.md`）。

---

## 2026-11-18｜重新審視進度：先用個人帳號寄信、名單來自整理好的 Excel

**改了哪些檔案**
- `PROGRESS.md`：狀態表改寫；補上 M3-04、M3-07～M3-11 漏填的完成日期；M1-12／M1-15／M2-01a／M3-04a 註記已過時的說法；M2-15 改成個人帳號驗收；新增 M2-19～M2-23；「開發中發現」更新（Excel 缺統編找誰補、mypy 行號、API 匯入去留、防呆文字寫死 14 天）
- `docs/SPEC.md` 第 11 節第 4、7 點：公司帳號之後再說；星等由整理好的 Excel 提供，系統沒有模型

**解決了什麼問題**
- 進度表有幾處和實際不符：幾個已完成的上層任務沒填日期；退訂行為已被 M3-17 改掉，舊任務說明沒註記；M2-15 還寫著等公司權限核准。
- 使用者確認：沒有模型，名單是自己整理好的 Excel 匯入後在網頁上看結果；真實寄信先用個人 Microsoft 帳號。

**做了哪些決定**
- 個人帳號要先寫 ADR 0007（M2-19）再寫程式：ADR 0005 的 On-Behalf-Of 對個人帳號是否可用沒有確認，「連結 Outlook」可能要改成授權碼流程。
- 介面上的「模型」字樣改成「匯入批次」等說法（M2-23），資料庫名稱 `model_run`、`run_id` 不改，避免動 migration。
- 這次沒有刪除任何任務；API 匯入（F-IMP-5）要不要移除先列在待確認。

**還沒處理的問題**
- 開發機能不能開 `MAIL_MODE=live`：CLAUDE.md 第 6 節第 3 點只允許正式環境，要使用者決定（M2-22）。
- CLAUDE.md 開頭「MLE 模型評分後」、名詞表的 `model_run`／盲標規則是否要改寫，要使用者同意才改。

**下一步**
- M2-19 → M2-20～M2-22 → M2-15；M2-23；M2-17；之後 M4-06a。

---

## 2026-11-18｜M2-18 測試收件者白名單

**改了哪些檔案**
- `backend/app/domain/send_guard.py`：`parse_allowlist`、`recipient_allowed`、防呆原因 `RECIPIENT_NOT_ALLOWED`
- `backend/app/config.py`、`.env.example`：`MAIL_ALLOWED_RECIPIENTS`
- `backend/app/services/campaign_service.py`：新增 `exclusions_for`，候選清單、建立批次、按寄出、worker 寄出前都走同一個函式，天數與白名單一律讀設定
- `backend/app/services/send_service.py`、`api/v1/campaigns.py`：改用 `exclusions_for`，建立批次與候選清單帶入設定
- `docs/SPEC.md` 7.5：白名單說明
- 測試：`test_mail_domain`（白名單規則）、`test_campaigns`（建立時排除、寄出前再擋、天數設定）

**解決了什麼問題**
- 真實寄信測試時，就算資料庫裡有真實客戶，名單外的收件者也寄不出去。
- 修 bug（先補測試）：建立批次時「最近寄過」固定用 14 天，沒讀 `RECENT_SEND_DAYS`，和寄出時的判斷不一致。

**做了哪些決定**
- `@網域` 只比對完整網域，不含子網域，也不比對字尾相同的網域。
- 白名單是空的就不限制；沒有聯絡人時只報「沒有聯絡人」，不重複報白名單。
- 前端不用改：防呆原因的中文由後端 `/campaigns/exclusion-reasons` 提供。

**還沒處理的問題**
- 「14 天內已經寄過」的中文固定寫 14，`RECENT_SEND_DAYS` 改成其他值時文字不會跟著變。
- 本機測試用 Postgres 的複製檔（`%LOCALAPPDATA%\howder\pginstall\bin`）有 32 個檔案不見，原因不明，已從 `.venv` 補回。
- M2-15 真實寄信需要使用者準備 Microsoft 365 測試租用戶、Entra 應用程式與測試帳號。

**下一步**
- M2-17，之後 M4-06a；帳號準備好後做 M2-15。

---

## 2026-11-18｜移除側欄收合；M3-18 取消退訂、M3-16 建立批次候選篩選

**改了哪些檔案**
- `frontend/src/components/AppLayout.tsx`、`AppLayout.module.css`：移除側欄收合功能與「TEST 測試模式」標籤，還原成 `f6e8811` 的側欄（使用者覺得排版與收合效果不好；已單獨 commit `58891af`）
- `backend/app/domain/company_rules.py`、`contact_rules.py`：`status_after_resubscribe`（`do_not_contact` → `approved`，其他不改）、`check_resubscribe_reason`
- `backend/app/services/contact_service.py`、`api/v1/contacts.py`：`POST /contacts/{id}/resubscribe`（主管／管理員、原因必填、寫 `activity_log`）
- `frontend/src/pages/recommendations/ContactConfirmDialog.tsx`、`ContactsSection.tsx`、`api/*`、`lib/labels.ts`：聯絡人區塊「取消退訂」按鈕（只有主管／管理員看到）與確認對話框
- `backend/app/api/v1/campaigns.py`、`companies.py`、`services/campaign_service.py`：`/campaigns/candidates` 沿用推薦清單的篩選參數（`_filtered` 改名為公開的 `apply_filters`，加 `has_filters`）
- `frontend/src/pages/campaigns/CampaignNewPage.tsx`、`Campaigns.module.css`、`api/endpoints.ts`、`hooks.ts`：搜尋（公司名稱／統編）、產業、星級篩選與「清除篩選」
- `backend/tests/test_contacts.py`、`test_campaigns.py`、前端 `ContactDialogs.test.tsx`、`Campaigns.test.tsx`：各條規則的測試（`test_m3_18_*`、`test_m3_16_*`）
- `docs/SPEC.md`、`PROGRESS.md`：候選名單 API 說明、任務勾選

**解決了什麼問題**
- 取消退訂原本沒有入口；客戶同意恢復聯絡時，主管／管理員可以處理，且公司不會卡在終點狀態。
- 建立批次頁候選公司很多時沒有搜尋與篩選。

**做了哪些決定**
- 取消退訂後公司退回「已通過」而不是退回退訂前的狀態：不用回頭翻 `activity_log`，也不會讓舊的寄信進度誤導業務；缺點是要重新產生草稿。`do_not_contact` 在一般狀態機仍是終點，只有這條規則能離開。
- 候選名單篩選放在後端（重用 `list_filters`），不在前端過濾，名單大時也只算需要的公司的防呆原因。
- 勾選的公司在換篩選後保留；「全選／全部取消」只動目前顯示的公司。

**還沒處理的問題**
- 這個 worktree 的 `pg_local` 會因為兩個 worktree 的 `.venv` 路徑不同而想重建共用的 Postgres 執行檔，與另一個工作階段衝突；這次用獨立的 `LOCALAPPDATA`／`HOWDER_TEST_PGDATA` 繞過，沒改程式。
- `uv run mypy app` 在 `api/v1/campaigns.py` 仍有 1 個既有錯誤（見 PROGRESS）。
- 候選名單篩選只做了搜尋、產業、星級三項；推薦清單其餘篩選（國別、來源…）後端已支援，前端要不要開放待決定。
- 建立批次頁的畫面是用舊後端（不含這次的篩選）檢查版面，篩選行為由自動化測試涵蓋，尚未用新後端在瀏覽器實測。

**下一步**
- M2-17；之後拆 M4（`PROGRESS.md`）。

---

## 2026-11-18｜M4 拆細（本機 LLM）、MLE 範圍調整、任務刪除規則

**改了哪些檔案**
- `PROGRESS.md`：M4 拆成 M4-06a～l、M4-07a～c、M4-08a～e、M4-02a～b、M4-01a～c、M4-09；刪除已取消的任務
- `docs/SPEC.md`：第 1 節目標、§4.5 改成「名單品質」、路由與 API 表、角色表、M4 驗收條件、11-10 改用本機 Ollama
- `CLAUDE.md`：開頭第 4 點改為「MLE 只負責產生名單 CSV，結果不回傳」；第 13 節改為不做的任務直接刪除
- `frontend/src/pages/AdminImportsPage.tsx`、`RejectDialog.tsx`、`backend/app/api/v1/reviews.py`：說明文字與註解拿掉「回饋給 MLE」

**解決了什麼問題**
- 規格原本假設結果要回饋給 MLE 重新訓練，和實際流程（MLE 只產生 CSV，後續都在本系統做完）不符。
- M4 原本只有大項，現在拆成一次一個 commit 的細項；AI 先用本機能跑的 Ollama＋`qwen3:8b`／`qwen3:14b`（RTX 5060 Laptop 8 GB）。

**做了哪些決定**
- 取消並刪除 M4-03（回饋匯出，F-MLE-2）、M4-04（盲標，F-MLE-3）、M4-05（模型品質，F-MLE-4）：MLE 不會再拿回饋資料，盲標還要花業務時間。
- M4-02 排除原因報表保留，改為內部的名單品質報表（F-MLE-1）。`gold_label` 表保留不用，不另寫 migration 刪除。
- 依使用者指示刪除 PROGRESS 中原本標成 `[~]` 的任務：M3-01（移到 M4-06）、M3-02（不讀信箱，ADR 0004）、M3-03（移到 M4-07）、M3-05（併入 M3-09），以及「開發中發現」中已改排進 M2-16、M2-17、M3-16、M3-18 的 4 項；另刪「審核 CSV 時間是否要台灣時間給 MLE」。
- 之後不做的任務直接刪除，原因記在 CHANGELOG（CLAUDE.md 第 13 節）。
- 自動化測試仍不連本機 Ollama，只在手動腳本與驗收時連。

**還沒處理的問題**
- 本機 Ollama 服務檢查時沒有回應，M4-06g 前要先啟動。
- 舊日誌與 commit 訊息仍提到已刪除的任務編號，依規定不修改。

**下一步**
- M3-18 取消退訂，接著 M2-17、M3-16；之後 M4-06a。

---

## 2026-11-18｜記錄 M2 待確認的決定；M3-17 退訂只標聯絡人、M2-16 待寄出狀態

**改了哪些檔案**
- `docs/SPEC.md`、`PROGRESS.md`：記錄使用者對 M2 待確認事項的決定（F-MAIL-4、F-MAIL-6、F-CASE-5、取消退訂 API、11-10 GPU、11-11 寄信是否自動認領），新增任務 M2-16、M2-17、M3-16～M3-18
- `CLAUDE.md`：第 3 節 Graph 改成「登入、寄信；不讀業務信箱，ADR 0004」；第 1、4 節的 `sync_replies`／同步回覆改成實際的 `case_daily`（每日催辦）（使用者確認後修改）
- `backend/app/domain/contact_rules.py`、`services/contact_service.py`、`api/v1/contacts.py`、`api/v1/cases.py`：退訂只標記該聯絡人；`whole_company` 或最後一位聯絡人退訂才改公司 `do_not_contact` 並結案（M3-17）
- `frontend/src/pages/recommendations/ContactConfirmDialog.tsx`、`pages/cases/CasePanel.tsx`：退訂對話框加「整家公司不再聯絡」勾選，說明文字依是否還有其他聯絡人改變
- `backend/migrations/versions/0011_campaign_status_ready.py`、`db/schema.sql`：`campaign.status` 加 `ready`（M2-16）
- `backend/app/services/campaign_service.py`：草稿都審完、還沒按寄出時批次狀態是 `ready`；前端 `labels.ts` 顯示「待寄出」，`CampaignsPage.tsx`「我的待辦」也算待寄出
- 測試：`test_contacts`、`test_cases`、`test_schema_0011`、`test_campaigns`；前端 `ContactDialogs`、`Cases`、`Campaigns`、`labels`

**解決了什麼問題**
- 一位聯絡人退訂就讓整家公司不再聯絡，太嚴；現在公司還有其他聯絡人時照常可寄，案件也照常進行。
- 批次全部核准後仍顯示「待審核」，業務看不出來只差按寄出；現在顯示「待寄出」並列在「我的待辦」。

**做了哪些決定**
- 「公司要不要改不再聯絡」規則放在 `domain/contact_rules.company_stops_contact`；前端只依案件聯絡人清單決定說明文字，不重判規則。
- 整家公司不再聯絡時，其他聯絡人不會被標成退訂（取消退訂時只需處理公司狀態）。
- `ready` 不做資料回填：既有批次在下一次草稿動作時才重算（尚未上線，沒有影響）。
- M3-17 時誤用 prettier 重排了 5 個前端檔案，另開 `style:` commit 還原，專案不使用 prettier。

**還沒處理的問題**
- `uv run mypy app` 在 `api/v1/campaigns.py:301` 有 1 個既有錯誤（M3-17 之前就存在），列在 `PROGRESS.md`「開發中發現」。
- 案件聯絡人退訂但公司仍可聯絡時，案件 `contact_id` 仍指向已退訂的人。
- 寄信要不要自動認領公司（SPEC 11-11）、GPU 主機（SPEC 11-10）。

**下一步**
- M3-18 取消退訂，接著 M2-17、M3-16；之後拆 M4。

---

## 2026-11-18｜M3 案件追蹤與總覽（閉環）、CSV 欄位規格 v1

**改了哪些檔案**
- `backend/migrations/versions/0006`～`0010`：案件 `sales_case`／回填 `case_update`、待辦 view `v_case_reminder`、`job.kind` 加 `case_daily`、CSV v1 欄位（`country`、`url_status`、`source`、`fit_stars`、`product_type`、`tags`、批次 `funnel`）、總覽 view `v_case_fact`／`v_company_fact`（`v_kpi_summary` 回覆率改用案件）
- `backend/app/domain/case_rules.py`：案件狀態機、回填驗證、帶動公司狀態（跳級依序走過）
- `backend/app/services/case_service.py`、`reminder_service.py`、`metrics_service.py`：寄出自動開案、加入追蹤、回填、退訂結案、每日催辦、總覽加總
- `backend/app/services/importer.py`、`api/v1/imports.py`：CSV v1 新欄位、`invalid` 網址略過、未知欄位提示、API 匯入帶 `funnel`
- `backend/app/api/v1/cases.py`、`reminders.py`、`overview.py`、`companies.py`（新篩選、`/companies/export`）、`meta.py`（`/dimensions` 回傳國別、來源、標籤）
- `frontend/src/pages/cases/`：`/cases` 列表、各狀態件數、時間軸、回填表單、客戶要求退訂
- `frontend/src/pages/overview/`：`/overview` KPI、名單漏斗、各來源回覆率、待辦提醒
- `frontend/src/pages/recommendations/`：小數星等、CSV v1 篩選、欄位自選（`lib/columns.ts`）、匯出、批次加入追蹤；`AdminImportsPage.tsx` 顯示略過列、提示、漏斗數字
- `docs/samples/import_v1_sample.csv`：給 MLE 的範例（假資料）；`.gitignore` 只放行 `docs/samples/*.csv`
- `docs/SPEC.md` 3.1、8.1、8.4、API 表同步；測試新增 `test_case_rules`、`test_cases`、`test_schema_0006`～`0010`、`test_import_v1`、`test_companies_v1`、`test_overview`，前端 `Cases`、`Overview`、`Recommendations`、`columns` 測試

**解決了什麼問題**
- 閉環完成：寄出 → 自動開案 → 業務人工回填（不讀信箱，ADR 0004）→ 公司狀態跟著走 → 逾期／該追蹤／無回應提醒 → 總覽數字。
- M3-14 示範（sandbox）：API 匯入 100 家假公司 → 審核 → 100 封寄出 → 一件回覆並成交 NT$180,000、一件洽談中設今天追蹤；總覽顯示寄出 100、回覆率 2.0%、成交 1、該追蹤了 1。
- 修 bug（示範時發現，先補測試）：寄信不會認領公司，業務的漏斗「已寄信」用 `company.owner_id` 篩選變成 0；改依案件負責業務計算。
- MLE 漏斗數字存在 JSONB 不保留順序，畫面改成依數字由大到小排。

**做了哪些決定**
- 「寄出」「回覆」「成交」只在 `v_case_fact` 定義：時間軸有 `sent` 才算寄出；回填過 replied／negotiating／won 算回覆。回覆率不再讀 `email_event`。
- 總覽範圍：名單數是共用名單池；寄出／回覆／成交依案件負責業務，業務只看自己的，主管可選業務或全團隊；日期區間套寄出日（台灣時間）。
- migration 編號：0008 給 `job.kind`，0009 給 CSV v1，0010 給總覽 view；已套用的 migration 沒有修改（ruff 對 migrations 關掉 E501）。
- 舊版 Excel 沒有「資料來源」欄照樣匯入並提示；重新匯入不會洗掉已知來源。檔案有來源欄時每列必填。
- 欄位自選和匯出共用同一組欄位 key；畫面的「推薦度」匯出成星等＋優先級兩欄；匯出不含聯絡人 email。

**還沒處理的問題**
- 寄信要不要自動認領公司（目前只有「認領」與「加入追蹤」會），待業務主管決定。
- 先前提出、仍待決定：一位聯絡人退訂就讓整家公司 `do_not_contact` 是否太嚴、取消退訂入口、地端 LLM 的 GPU 主機、`CLAUDE.md` 第 3 節仍寫 Graph「讀回覆」（和 ADR 0004 衝突）、寄送下班時間上限、批次全部核准後的狀態文字、建立批次頁沒有搜尋。
- M2-15 真實 Outlook 驗收（等 SPEC 11-4）、M1-03 Docker 驗證。
- 其他小問題列在 `PROGRESS.md`「開發中發現」：對話框關閉後焦點、篩選列太長、比例門檻寫在兩處。

**下一步**
- 依 CLAUDE.md 第 13 節把 M4 拆成 commit 大小的任務，從 M4-06（地端 LLM 產生郵件，ADR 0006）開始。

---

## 2026-11-18｜M2 寄信：模板、批次、預覽佇列、寄出（sandbox）

**改了哪些檔案**
- `backend/migrations/versions/0005_template_versions_and_text_body.py`：模板版本（`family_id`、同一家族只有一個使用中版本）、純文字內文
- `backend/app/domain/template_rules.py`：變數白名單、渲染、跳脫 HTML、強制附退訂說明
- `backend/app/domain/send_guard.py`、`draft_rules.py`、`send_limits.py`：寄送防呆、草稿狀態機與改稿幅度、每日上限／每分鐘限速排程（台灣時間）
- `backend/app/services/`：`template_service`、`campaign_service`、`generator`、`draft_service`、`send_service`、`mailer`（Sandbox／Graph）、`mail_token`（OBO＋Fernet）、`jobs`（重試與改期）
- `backend/app/workers/`：`python -m app.workers`，LISTEN `job_queued` 立即處理
- `backend/app/api/v1/templates.py`、`campaigns.py`、`mail_connection.py`：模板管理、批次／草稿／寄出、Outlook 連結
- `backend/scripts/seed_templates.py`：初版模板（佔位文字，等 SPEC 11-5）
- `frontend/src/pages/AdminTemplatesPage.tsx`：模板列表、編輯、插入變數、假資料預覽
- `frontend/src/pages/campaigns/`：`/campaigns` 列表、`/campaigns/new` 建立批次、`/campaigns/:id` 預覽佇列與寄出、Outlook 連結提示
- `frontend/src/api/*`、`lib/labels.ts`：批次／草稿型別、hooks（產生中與寄送中每 2 秒更新）、錯誤訊息與狀態中文
- `frontend/src/components/AppLayout.tsx`：導覽列開放「邀請信」；`KpiCards.tsx` 提示文字更新
- 測試：`backend/tests/test_mail_domain.py`、`test_campaigns.py`、`test_mail_connection.py`、`test_templates.py`；`frontend/src/pages/campaigns/Campaigns.test.tsx`、`AdminTemplatesPage.test.tsx`
- `CLAUDE.md` 第 3 節：加上 worker 指令

**解決了什麼問題**
- 業務可以從「已通過」的公司建立批次，產生草稿、逐封修改核准（Ctrl+Enter 核准並跳下一封）、全部核准（要按兩次）、立即或排程寄出。
- 系統不會自動寄信：只有 `approved` 的草稿會排進寄送工作，建立批次、按寄出、worker 真正寄出前各檢查一次防呆。
- sandbox 端到端（M2-13）：10 家 → 產生 → 改一封 → 核准 → 寄出，`email_message` 10 筆、公司都變 `sent`、改過的那封 `edit_ratio` 0.030。
- 修 bug：API 的 `contact_id` 可以不填，但後端判成「沒有聯絡人」；改成用該公司第一位沒退訂的聯絡人（先寫重現測試）。

**做了哪些決定**
- 預覽佇列直接放在 `/campaigns/:id`，不另開 `/review`（SPEC 6.2 已同步）。
- 寄出只限批次負責業務本人（信從本人信箱寄）；主管可以看、可以審，但不能代寄。
- 失敗的草稿要先存一次（回到待審核）才能再核准；防呆沒過的原因存成 `GUARD:代碼` 給前端翻成中文。
- Outlook 權杖失效時暫停（不算失敗），重新連結後自動恢復排程。
- 寄送時間從每天 9 點開始（`SEND_DAY_START_HOUR`），本機端到端測試時用環境變數設成 0。

**還沒處理的問題**
- M2-15 真實 Outlook 驗收：等 Microsoft 365 管理員核准 `Mail.Send`（SPEC 11-4）。
- 模板內文還是佔位文字（SPEC 11-5）。
- 前端 bundle 超過 500 kB 的警告仍在（已列在 PROGRESS）。
- 一位聯絡人退訂就封鎖整家公司是否太嚴、「取消退訂」入口，仍待業務主管決定。
- `CLAUDE.md` 第 3 節外部服務仍寫 Graph「讀回覆」，和 ADR 0004（不讀信箱）不一致，等使用者決定是否修改。

**下一步**
- 把 M3 拆成 commit 大小的任務，從 M3-07 `sales_case` migration、M3-08 案件 domain 規則開始；寄出成功時自動開案接到 M2-07d 的 worker。

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
