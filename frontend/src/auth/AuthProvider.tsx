// 登入狀態。dev 模式把 email 存在 localStorage，每個請求帶 X-Dev-User；entra 模式帶 Bearer token。
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { configureAuth } from "../api/client";
import { getMe } from "../api/endpoints";
import type { User } from "../api/types";

export const AUTH_MODE = import.meta.env.VITE_AUTH_MODE === "entra" ? "entra" : "dev";
const DEV_KEY = "howder.devUser";

// MSAL 很大，只有 entra 模式才下載（dev 模式完全不載入）
const loadMsal = () => import("./msal");

type Status = "loading" | "signedOut" | "signedIn";

interface AuthState {
  status: Status;
  user: User | null;
  error: string | null;
  loginDev: (email: string) => Promise<void>;
  loginEntra: () => Promise<void>;
  logout: () => void;
  isManager: boolean;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthState | null>(null);

function readDevUser(): string | null {
  try {
    return localStorage.getItem(DEV_KEY);
  } catch {
    return null;
  }
}

function writeDevUser(email: string | null): void {
  try {
    if (email) localStorage.setItem(DEV_KEY, email);
    else localStorage.removeItem(DEV_KEY);
  } catch {
    // 無痕模式等情況存不了，只影響重新整理後要再登入一次
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [devEmail, setDevEmail] = useState<string | null>(() => (AUTH_MODE === "dev" ? readDevUser() : null));

  const signOutLocal = useCallback(() => {
    writeDevUser(null);
    setDevEmail(null);
    setUser(null);
    setStatus("signedOut");
  }, []);

  // 告訴 API client 怎麼附上登入資訊
  useEffect(() => {
    configureAuth(async (): Promise<Record<string, string>> => {
      if (AUTH_MODE === "dev") return devEmail ? { "X-Dev-User": devEmail } : {};
      return { Authorization: `Bearer ${await (await loadMsal()).entraToken()}` };
    }, signOutLocal);
  }, [devEmail, signOutLocal]);

  const loadMe = useCallback(async () => {
    try {
      setUser(await getMe());
      setStatus("signedIn");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "登入失敗");
      setUser(null);
      setStatus("signedOut");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (AUTH_MODE === "dev") {
        if (devEmail) await loadMe();
        else setStatus("signedOut");
        return;
      }
      const account = await loadMsal()
        .then((m) => m.initEntra())
        .catch(() => null);
      if (cancelled) return;
      if (account) await loadMe();
      else setStatus("signedOut");
    })();
    return () => {
      cancelled = true;
    };
  }, [devEmail, loadMe]);

  const value = useMemo<AuthState>(
    () => ({
      status,
      user,
      error,
      loginDev: async (email: string) => {
        const clean = email.trim().toLowerCase();
        writeDevUser(clean);
        setStatus("loading");
        setDevEmail(clean);
      },
      loginEntra: async () => (await loadMsal()).entraLogin(),
      logout: () => {
        signOutLocal();
        if (AUTH_MODE === "entra") void loadMsal().then((m) => m.entraLogout());
      },
      isManager: user?.role === "manager" || user?.role === "admin",
      isAdmin: user?.role === "admin",
    }),
    [status, user, error, signOutLocal],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth 必須放在 AuthProvider 裡");
  return ctx;
}
