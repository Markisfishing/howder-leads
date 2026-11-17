// 呼叫後端的唯一入口：頁面不直接寫 fetch（CLAUDE.md 第 4 節第 1 點）
import { errorMessage } from "./errorMessages";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: unknown;

  constructor(code: string, status: number, serverMessage: string, details?: unknown) {
    super(errorMessage(code, serverMessage));
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

// 由 AuthProvider 設定：回傳要附在每個請求上的登入 header
type AuthHeaderGetter = () => Promise<Record<string, string>>;
let getAuthHeaders: AuthHeaderGetter = async () => ({});
let onUnauthorized: () => void = () => {};

export function configureAuth(getter: AuthHeaderGetter, unauthorized: () => void): void {
  getAuthHeaders = getter;
  onUnauthorized = unauthorized;
}

type Query = Record<string, string | number | boolean | Array<string | number> | null | undefined>;

export function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === null || value === undefined || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => params.append(key, String(v)));
    else params.set(key, String(value));
  }
  const qs = params.toString();
  return `/api/v1${path}${qs ? `?${qs}` : ""}`;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  query?: Query;
  json?: unknown;
  form?: FormData;
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { ...(await getAuthHeaders()) };
  let body: BodyInit | undefined;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  } else if (options.form) {
    body = options.form;
  }
  let res: Response;
  try {
    res = await fetch(buildUrl(path, options.query), { method: options.method ?? "GET", headers, body });
  } catch {
    throw new ApiError("NETWORK_ERROR", 0, "無法連線到伺服器");
  }
  if (!res.ok) {
    let code = "HTTP_ERROR";
    let message = res.statusText;
    let details: unknown;
    try {
      const data = (await res.json()) as { error?: { code: string; message: string; details?: unknown } };
      if (data.error) ({ code, message, details } = data.error);
    } catch {
      // 回應不是 JSON，保留 statusText
    }
    if (res.status === 401) onUnauthorized();
    throw new ApiError(code, res.status, message, details);
  }
  return res;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const res = await send(path, options);
  return (await res.json()) as T;
}

export async function apiBlob(path: string): Promise<Blob> {
  return (await send(path, {})).blob();
}
