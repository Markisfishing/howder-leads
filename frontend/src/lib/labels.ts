// 程式代碼 → UI 中文（CLAUDE.md 第 2 節的專有名詞）
import type { CompanyStatus, ContactSource, RejectReason } from "../api/types";

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
  contact_add: "新增聯絡人",
  contact_update: "修改聯絡人",
  contact_unsubscribe: "聯絡人退訂",
  contact_delete: "刪除聯絡人個資",
};

export const CONTACT_SOURCE_LABELS: Record<ContactSource, string> = {
  website: "公司官網",
  business_card: "名片",
  referral: "別人介紹",
  exhibition: "展覽",
  manual: "其他（手動輸入）",
};

const CONTACT_FIELD_LABELS: Record<string, string> = {
  email: "email",
  source: "來源",
  name: "姓名",
  title: "職稱",
  is_verified: "確認狀態",
};

/** 往來紀錄的備註：聯絡人的紀錄後端只存代碼（不存個資），這裡翻成中文 */
export function activityNote(action: string, note: string | null): string | null {
  if (!note) return null;
  if (action === "contact_add") return `來源：${CONTACT_SOURCE_LABELS[note as ContactSource] ?? note}`;
  if (action === "contact_update")
    return `改了${note
      .split(",")
      .map((f) => CONTACT_FIELD_LABELS[f] ?? f)
      .join("、")}`;
  return note;
}

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
