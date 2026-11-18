# 0008 測試階段先用共用的 Outlook.com 信箱，以 SMTP＋密碼寄信

- 日期：2026-11-18
- 狀態：**採用（負責人決定）**；只限開發環境。2026-11-18 實測：outlook.com 信箱回 `535`，密碼登入 SMTP 已被 Microsoft 停用（2024-09-16 起），**這個信箱不能用**；`SmtpMailer` 本身不綁 Outlook，可改用其他支援應用程式密碼的 SMTP（例如 Gmail），或改走 ADR 0007
- 相關：ADR 0005（業務本人 Outlook、Graph）、ADR 0007（個人帳號 OAuth，暫緩）、SPEC 7.5、PROGRESS M2-24、M2-25、M2-15

## 背景
ADR 0005／0007 的 Graph 寄信要先在 Azure 入口網站註冊應用程式，負責人目前不想走這一步。負責人決定：測試階段先用一個專門的空殼 outlook.com 信箱，系統用 SMTP＋密碼從這個信箱寄出，只寄到白名單裡負責人自己的收件信箱。

## 決定
1. 新增設定 `MAIL_TRANSPORT`：`graph`（預設，維持 ADR 0005）或 `smtp`（這份 ADR）。
2. `smtp` 時用 `SMTP_HOST`（預設 `smtp-mail.outlook.com`）、`SMTP_PORT`（587，STARTTLS）、`SMTP_USERNAME`（共用信箱地址，也是寄件人）、`SMTP_PASSWORD`、`SMTP_FROM_NAME`。密碼只放 `backend/.env`，不 commit、不印進 log。
3. `smtp` **只限開發環境**：`ENV=production` 設 `smtp` 啟動失敗；`ENV=test` 一律不可以 live；開發環境照 M2-22 必須有收件者白名單。
4. 用 `smtp` 時不需要 `AUTH_MODE=entra`、client secret、`MAIL_TOKEN_KEY`，也不需要「連結 Outlook」（API 回 `not_required`，前端橫幅改成提示共用信箱）。
5. 寄送流程、核准、防呆、白名單、限速都不變：`SmtpMailer` 只是 `Mailer` 介面的另一個實作（`backend/app/services/mailer.py`）。
6. `email_message.graph_message_id` 存 SMTP 的 `Message-ID`；`conversation_id` 留空。
7. 登入失敗（535）不重試，草稿標為失敗、代碼 `SMTP_AUTH_FAILED`；4xx 暫時性錯誤與連線錯誤照佇列重試。
8. 提供 `scripts/smtp_check.py`，由信箱擁有人自己執行，確認還能不能用密碼登入；開發者與 AI 不代為登入。

## 理由
- 不用註冊 Azure 應用程式，負責人今天就能測寄信。
- 改動只在寄信那一層，之後換回 Graph（公司帳號）只改 `.env` 的 `MAIL_TRANSPORT`。

## 代價與風險
- **Microsoft 正在停用 outlook.com 的「密碼登入 SMTP」**，這個信箱很可能已經登入不了（會收到 535）。先跑 `smtp_check`；登入不了就回到 ADR 0007 的 Graph 授權（M2-20、M2-21）。
- 所有業務共用一個寄件信箱，**不是**「從業務本人的 Outlook 寄出」：客戶看到的寄件人、寄件備份、客戶回信都在這個共用信箱，業務要去那裡看回信再回填。所以只用在測試。
- 系統要保存信箱密碼（`.env`），外洩風險比 OAuth 權杖高；建議這個信箱只用來測試、開兩步驟驗證後若不能登入 SMTP 就改走 ADR 0007。
- 新的個人信箱可能被 Microsoft 限制寄送量或要求驗證；測試用 `DAILY_SEND_LIMIT=10`、`SEND_PER_MINUTE=1`。
