# 0007 先用個人 Microsoft 帳號測試登入與寄信：可切換的 authority，連結 Outlook 改用授權碼流程

- 日期：2026-11-18
- 狀態：**提議，等負責人確認**（確認前不寫程式）。2026-11-18 負責人決定測試階段先用共用信箱 SMTP（ADR 0008），本 ADR 暫緩；SMTP 登入不了、或之後換公司帳號時再做
- 相關：ADR 0005（OBO）、SPEC 7.5、11-4、PROGRESS M2-20～M2-22、M2-15

## 背景
公司 Microsoft 365 帳號的 `Mail.Send` 核准還沒有結果（SPEC 11-4）。要先用一個專門測試用的個人 outlook.com 帳號當寄件人，只寄到負責人自己的信箱（白名單，M2-22）。ADR 0005 目前的設計是：前端用 MSAL 登入公司租用戶 → 後端用 On-Behalf-Of（OBO）換 Graph 權杖。

## 查到的事實（官方文件，2026-11-18 查）
1. **個人帳號可以登入自己註冊的應用程式。** 註冊時「支援的帳戶類型」可選「僅個人 Microsoft 帳戶」，或「任何組織目錄中的帳戶＋個人帳戶」（多租用戶）。個人帳號的租用戶 ID 固定是 `9188040d-6c67-4c5b-b112-36a304b66dad`，別名 `consumers`；`common` 同時接受公司與個人帳號。
   - [註冊應用程式](https://learn.microsoft.com/en-us/graph/auth-register-app-v2)、[OIDC 與 authority](https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc)
2. **自己的 API 要接受個人帳號的 token，必須接受 v2.0 token：** 應用程式資訊清單 `accessTokenAcceptedVersion` 設成 `2`（`null` 會變成 v1.0）。個人帳號 token 的 issuer 是 `https://login.microsoftonline.com/9188040d-6c67-4c5b-b112-36a304b66dad/v2.0`，必須完全相符。Microsoft 也不建議把已經存在的註冊改成支援個人帳號，**建議另外新註冊一個**。
   - [Access tokens](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens)、[受保護的 Web API 設定](https://learn.microsoft.com/en-us/entra/identity-platform/scenario-protected-web-api-app-configuration)
3. **Graph `Mail.Send`（委派）個人帳號可用**，只能用 `POST /me/sendMail`，信會存進本人的寄件備份。個人帳號沒有應用程式權限（app-only），只有委派權限，而且第一次授權一定要本人在 Microsoft 頁面按同意。
   - [user: sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0)、[權限參考](https://learn.microsoft.com/en-us/graph/permissions-reference)
4. **OBO 能不能用在個人帳號：文件沒有明講。** 找不到官方說「支援」或「不支援」。**沒有查到的，不當成可以用。**
5. **沒查到** sendMail 對個人帳號的每日上限數字；新註冊的個人帳號可能被限制寄送或要求驗證。

## 決定（提議）
1. **登入**：維持「前端 MSAL 登入 → 後端驗證 access token」，但後端的 authority 做成設定 `ENTRA_AUTHORITY`（`consumers`／`common`／`organizations`／租用戶 ID；預設維持公司租用戶，行為不變）。issuer 驗證**不可以關掉**，改成「允許的 issuer 清單」：測試期是個人帳號的固定 issuer；之後加公司租用戶就多一筆。
2. **新註冊一個應用程式**專給測試用（支援帳戶類型：任何組織目錄＋個人帳戶，之後換公司帳號不用重註冊；`accessTokenAcceptedVersion: 2`）。公司的應用程式之後另外註冊，不改這個。
3. **「連結 Outlook」改成授權碼流程（PKCE＋機密用戶端）**，不再用 OBO。scopes：`Mail.Send`、`User.Read`、`offline_access`。理由：OBO 對個人帳號沒有保證；授權碼流程個人與公司帳號都支援，換公司帳號時**不用改程式**，只改設定。
   - 後端 `GET /me/mail-connection/start` 回傳授權網址（帶 `state`＋PKCE），`GET /me/mail-connection/callback` 驗證 `state`、換 token。
   - `state` 綁定目前登入的使用者、短時間過期，用 `MAIL_TOKEN_KEY` 加密成 Fernet 字串，不新增資料表。
   - token 快取照 ADR 0005：MSAL 快取用 Fernet 加密存在 `user_mail_credential.token_cache`，worker 用 `acquire_silent`，**worker 與資料表都不用改**。
4. ADR 0005 的 OBO 部分標為「被 0007 取代（連結流程）」；其餘（加密、`needs_reconnect`、只用本人權杖、`Mail.Send` 最小權限）維持。

## 理由
- 不依賴文件沒保證的行為；個人與公司帳號用同一套流程，之後切換只改 `.env`。
- 改動集中在登入驗證與「連結」兩處，寄信、排程、防呆、白名單都不動。

## 代價與風險
- 業務要多按一次 Microsoft 的同意畫面（OBO 不用）；公司上線後若管理員一次同意全公司，畫面會省略。
- 多寫 start／callback 兩支 API 和前端導向；`state` 和 redirect URI 設錯會連不上。
- 要管理 client secret 與 `MAIL_TOKEN_KEY`，只放 `.env`，不 commit。
- 個人帳號的寄送量限制未知；測試先用 `DAILY_SEND_LIMIT=10`、`SEND_PER_MINUTE=1`。

## 需要負責人做的事
1. 確認上面的決定（尤其是 3：改授權碼流程）。
2. 用**寄件測試帳號**登入 Azure 入口網站，新註冊應用程式：支援帳戶類型選「任何組織目錄＋個人帳戶」；資訊清單 `accessTokenAcceptedVersion` 設 `2`；平台 SPA 重新導向 `http://localhost:5173`，網頁平台重新導向後端 callback（路徑依 M2-21 定案）；公開 `access_as_user` 範圍。
3. 建立 client secret 與 `MAIL_TOKEN_KEY`（指令在 `.env.example`）**自己**填進 `backend/.env`。client ID 不是機密，可以告訴開發者。**密碼與 secret 不要貼進對話。**
4. 若個人帳號無法註冊應用程式（可能要先有預設目錄／免費 Azure 帳號），回報給開發者，ADR 改成「等公司帳號」。

## 後續
M2-20（登入）、M2-21（連結）依這份決定修細；M2-15 驗收在兩者完成後做。
