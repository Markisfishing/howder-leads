# 0005 Outlook 寄信權杖：On-Behalf-Of 取得委派權杖，加密存在資料庫

- 日期：2026-11-17
- 狀態：採用
- 相關：SPEC 7.5、9（安全）、ADR 0003（佇列）、ADR 0004（只申請 `Mail.Send`）

## 背景
信要從業務本人的信箱寄出（委派權限 `Mail.Send`），但寄送是 worker 在背景做的（排程、限速、隔天補寄），那時業務不一定開著網頁。所以後端必須能在業務不在線上時，代他取得 Graph 權杖。

考慮過的做法：
| 做法 | 優點 | 缺點 |
|---|---|---|
| A. 應用程式權限 `Mail.Send`（app-only） | 不用存任何業務的權杖 | 預設可以用**全公司任何人**的名義寄信，必須再請 Exchange 管理員設存取限制；管理員通常不願意核准 |
| B. 另做一套「連結 Outlook」的授權碼流程 | 標準做法 | 業務登入後還要再跳一次 Microsoft 頁面；要多寫 redirect 處理 |
| **C. On-Behalf-Of（OBO）** | 業務已經用 Entra 登入，前端送來的 access token（audience 是本系統）直接換成 Graph 權杖，不用再跳頁 | 要存 refresh token，必須加密 |

## 決定
採用 **C. On-Behalf-Of**：
1. 本系統的 Entra 應用程式改成機密用戶端（新增 client secret 或憑證，只放 `.env`／金鑰庫）。委派權限只有 `Mail.Send`、`offline_access`、`User.Read`，由租用戶管理員**一次性代表全公司同意**（SPEC 11-4），業務不會看到同意畫面。
2. 業務在「邀請信」頁按「連結 Outlook」：前端呼叫 `POST /api/v1/me/mail-connection`，後端用 MSAL Python 的 `ConfidentialClientApplication.acquire_token_on_behalf_of()` 拿到 Graph 權杖。這一步同時確認權限真的拿得到，不會等到寄信才失敗。
3. MSAL 的權杖快取（含 refresh token）序列化後用 **Fernet**（`cryptography`，AES-128-CBC + HMAC）加密，存進 `user_mail_credential.token_cache`（`BYTEA`），**一位業務一筆**。金鑰放在 `MAIL_TOKEN_KEY`，用 `MultiFernet` 支援換金鑰。
4. worker 寄信時，只讀**這封信寄件人本人**的那一筆，解密後呼叫 `acquire_token_silent()`，需要時自動用 refresh token 換新，再把更新後的快取加密寫回。
5. refresh token 失效時（約 90 天沒用、密碼重設、管理員撤銷），把 `status` 設成 `needs_reconnect`，該業務的待寄信件暫停，標示 `MAIL_AUTH_REQUIRED`。業務的畫面和待辦清單提示「請重新連結 Outlook」，重新連結後自動恢復。
6. 業務可以「中斷連結」：直接刪除那一筆（權杖不需要保留稽核），寫一筆 `activity_log`。
7. `MAIL_MODE=sandbox` 時完全不呼叫 Graph，也不需要連結；`AUTH_MODE=dev` 沒有 Entra token，只能用 sandbox。

## 資料表（M2-11 的 migration 0003 建立）
```
user_mail_credential
  user_id        BIGINT PRIMARY KEY REFERENCES app_user
  token_cache    BYTEA NOT NULL        -- Fernet 加密後的 MSAL 快取
  scopes         TEXT[] NOT NULL       -- 實際拿到的權限
  status         TEXT NOT NULL CHECK (status IN ('connected','needs_reconnect'))
  connected_at   TIMESTAMPTZ NOT NULL DEFAULT now()
  last_used_at   TIMESTAMPTZ
  last_error     TEXT                  -- 錯誤代碼，不放權杖內容
```

## 安全規則（寫測試）
- 權杖、快取、`MAIL_TOKEN_KEY`、client secret 不出現在 log、錯誤訊息、API 回應。
- `GET /me/mail-connection` 只回傳 `status`、`connected_at`、`scopes`，不回傳任何權杖內容。
- worker 只能用寄件人本人的權杖；主管或管理員也不能用別人的信箱寄信。
- 測試一律用假的 OBO／Graph 實作（CLAUDE.md 第 6 節第 4 點）。
- `MAIL_MODE=live` 時如果 `MAIL_TOKEN_KEY` 或 client secret 沒設，系統啟動就失敗。

## 理由
- 業務不用多跳一次登入，寄信一定是「本人信箱、本人寄件備份」，符合 SPEC 7.5。
- 權限範圍最小：只有 `Mail.Send`，而且只能代**已經連結的本人**寄信，不會變成能用任何人名義寄信的 app-only 權限。
- 加密金鑰和資料庫分開放，資料庫外洩時拿不到可用的權杖。

## 代價
- 要管理 client secret（建議用憑證，到期前要換）和 `MAIL_TOKEN_KEY`。
- 業務約 90 天沒寄信，就要重新連結一次。
- 需要新增 Python 套件 `msal`；`cryptography` 已經透過 `pyjwt[crypto]` 安裝。
