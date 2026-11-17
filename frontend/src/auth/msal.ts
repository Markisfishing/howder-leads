// Microsoft Entra ID 登入（VITE_AUTH_MODE=entra）。前端取得 access token，後端驗證（backend/app/services/auth.py）
import {
  InteractionRequiredAuthError,
  PublicClientApplication,
  type AccountInfo,
} from "@azure/msal-browser";

const clientId = import.meta.env.VITE_ENTRA_CLIENT_ID ?? "";
const tenantId = import.meta.env.VITE_ENTRA_TENANT_ID ?? "";
// 後端在 Entra「公開 API」設定的 scope
const scopes = [`api://${clientId}/access_as_user`];

let instance: PublicClientApplication | null = null;

async function getInstance(): Promise<PublicClientApplication> {
  if (!instance) {
    const app = new PublicClientApplication({
      auth: {
        clientId,
        authority: `https://login.microsoftonline.com/${tenantId}`,
        redirectUri: window.location.origin,
      },
      cache: { cacheLocation: "sessionStorage" },
    });
    await app.initialize();
    instance = app;
  }
  return instance;
}

/** 頁面載入時處理登入轉址回來的結果，回傳目前帳號（沒登入回傳 null） */
export async function initEntra(): Promise<AccountInfo | null> {
  const app = await getInstance();
  const result = await app.handleRedirectPromise();
  const account = result?.account ?? app.getAllAccounts()[0] ?? null;
  if (account) app.setActiveAccount(account);
  return account;
}

export async function entraLogin(): Promise<void> {
  await (await getInstance()).loginRedirect({ scopes });
}

export async function entraLogout(): Promise<void> {
  await (await getInstance()).logoutRedirect();
}

export async function entraToken(): Promise<string> {
  const app = await getInstance();
  const account = app.getActiveAccount();
  if (!account) throw new Error("尚未登入");
  try {
    return (await app.acquireTokenSilent({ scopes, account })).accessToken;
  } catch (err) {
    if (err instanceof InteractionRequiredAuthError) await app.acquireTokenRedirect({ scopes, account });
    throw err;
  }
}
