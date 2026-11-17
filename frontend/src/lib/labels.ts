// 程式代碼 → UI 中文（CLAUDE.md 第 2 節的專有名詞）
import type { CompanyStatus, RejectReason } from "../api/types";

export const STATUS_LABELS: Record<CompanyStatus, string> = {
  imported: "已匯入",
  pending_review: "待審",
  approved: "已通過",
  rejected: "已排除",
  drafted: "草稿已產生",
  draft_approved: "草稿已核准",
  sent: "已寄出",
  replied: "已回覆",
  meeting: "會議",
  won: "成交",
  lost: "失敗",
  do_not_contact: "不再聯絡",
};

export type Tone = "success" | "warning" | "danger" | "info" | "neutral";

export const STATUS_TONE: Record<CompanyStatus, Tone> = {
  imported: "neutral",
  pending_review: "neutral",
  approved: "success",
  rejected: "danger",
  drafted: "info",
  draft_approved: "info",
  sent: "info",
  replied: "success",
  meeting: "success",
  won: "success",
  lost: "neutral",
  do_not_contact: "danger",
};

export const REJECT_REASON_LABELS: Record<RejectReason, string> = {
  wrong_industry: "產業判斷錯誤",
  existing_customer: "已經是客戶",
  competitor: "競爭對手",
  wrong_website: "官網錯誤",
  no_demand: "沒有端子台需求",
  closed_business: "已歇業",
  other: "其他",
};

export const LIKELIHOOD_TONE: Record<string, Tone> = { 高: "success", 中: "warning", 低: "neutral" };

export const PRIORITY_LABELS: Record<string, string> = {
  A: "第一優先",
  B: "可開發",
  C: "觀察／策略",
  D: "暫不優先",
};

export const ACTIVITY_LABELS: Record<string, string> = {
  import: "匯入",
  status_change: "狀態變更",
  claim: "認領",
  release: "釋出",
  assign: "重新分派",
  update_website: "修正官網",
  update_industry: "修正產業",
  note: "備註",
  manual_add: "手動加入",
};

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("zh-TW", { dateStyle: "medium", timeZone: "Asia/Taipei" }).format(new Date(iso));
}

export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat("zh-TW", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Asia/Taipei",
  }).format(new Date(iso));
}

export function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
