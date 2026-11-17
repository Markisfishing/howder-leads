// 和後端 API 回應對應的型別（backend/app/api/v1/*.py）

export type Role = "sales" | "manager" | "admin";

export type CompanyStatus =
  | "imported"
  | "pending_review"
  | "approved"
  | "rejected"
  | "drafted"
  | "draft_approved"
  | "sent"
  | "replied"
  | "meeting"
  | "won"
  | "lost"
  | "do_not_contact";

export type RejectReason =
  | "wrong_industry"
  | "existing_customer"
  | "competitor"
  | "wrong_website"
  | "no_demand"
  | "closed_business"
  | "other";

export interface User {
  user_id: number;
  email: string;
  display_name: string;
  role: Role;
  is_active: boolean;
}

export interface CompanyRow {
  company_id: number;
  tax_id: string;
  name: string;
  website_url: string | null;
  website_verified: boolean;
  status: CompanyStatus;
  owner_id: number | null;
  owner_name: string | null;
  owner_locked_until: string | null;
  added_manually: boolean;
  priority: "A" | "B" | "C" | "D" | null;
  stars: number;
  score: string | null;
  likelihood: "高" | "中" | "低" | null;
  is_competitor: boolean;
  industry_id: number | null;
  industry: string | null;
  customer_type: string | null;
  reason: string | null;
  updated_at: string;
  // CSV 欄位規格 v1（M3-06c）；fit_stars 是小數字串（例如 "4.5"），沒給時後端用優先級星等補上
  country: string;
  url_status: "valid" | "invalid" | "unchecked";
  source: string | null;
  fit_stars: string | null;
  product_type: string | null;
  tags: string[];
}

export interface CompanyPage {
  items: CompanyRow[];
  total: number;
  page: number;
  page_size: number;
}

export interface Activity {
  action: string;
  from_value: string | null;
  to_value: string | null;
  note: string | null;
  user: string | null;
  created_at: string;
}

export interface ReviewRecord {
  decision: "approved" | "rejected";
  reject_reason: RejectReason | null;
  note: string | null;
  reviewer: string | null;
  created_at: string;
}

/** 聯絡人來源，和後端 migration 0004 的 CHECK 一致 */
export type ContactSource = "website" | "business_card" | "referral" | "exhibition" | "manual";

export interface Contact {
  contact_id: number;
  name: string | null;
  title: string | null;
  email: string;
  source: ContactSource;
  is_verified: boolean;
  unsubscribed: boolean;
}

export interface CompanyDetail extends CompanyRow {
  registered_products: string | null;
  model_industry_id: number | null;
  run_id: number | null;
  priority_label: string | null;
  priority_definition: string | null;
  suggested_action: string | null;
  contacts: Contact[];
  reviews: ReviewRecord[];
  activities: Activity[];
}

export interface Kpis {
  pending_review: number;
  total_companies: number;
  five_star: number;
  sent_7d: number;
  sent_total: number;
  replied_total: number;
  reply_rate: string | null;
  won_total: number;
  won_amount_twd: string;
}

// ---------- 總覽（M3-12b、F-DASH-1～4）----------
export interface OverviewQuery {
  from: string | null;
  to: string | null;
  industry: number | null;
  product_type: string;
  owner: number | null;
}

export interface Overview {
  scope_owner_id: number | null;
  kpis: {
    companies: number;
    high_priority: number;
    sent: number;
    replied: number;
    reply_rate: string | null;
    won: number;
    won_amount_twd: string;
  };
  funnel: { key: string; label: string; count: number; rate: string | null }[];
  mle_funnel: Record<string, number> | null;
  by_source: { source: string; sent: number; replied: number; reply_rate: string | null; insufficient: boolean }[];
  reminders: { kind: string; label: string; count: number }[];
}

export interface Dimensions {
  industries: { industry_id: number; name: string; is_prospect: boolean }[];
  priorities: { priority: string; label: string; definition: string; suggested_action: string; stars: number }[];
  reject_reasons: RejectReason[];
  statuses: CompanyStatus[];
  users: { user_id: number; display_name: string; role: Role }[];
  countries: string[];
  sources: string[];
  tags: string[];
}

export interface ImportRow {
  row: number;
  tax_id: string;
  name: string;
  priority: string;
  industry_id: number | null;
  likelihood: string | null;
  is_competitor: boolean;
  website_url: string | null;
  // CSV 欄位規格 v1（SPEC 8.4）；舊批次的資料列沒有這些欄位
  country?: string;
  url_status?: "valid" | "invalid" | "unchecked";
  source?: string | null;
  fit_stars?: number | null;
  action: "create" | "update" | "unchanged" | "skip";
  changed_fields?: string[];
}

export interface ImportError {
  row: number;
  field: string;
  message: string;
}

export interface ImportBatch {
  batch_id: number;
  file_name: string | null;
  source: string;
  status: "previewed" | "committed" | "cancelled";
  model_name: string | null;
  run_id: number | null;
  rows_total: number;
  rows_created: number;
  rows_updated: number;
  rows_unchanged: number;
  rows_error: number;
  created_at: string;
  funnel: Record<string, number> | null;
}

export interface ImportBatchDetail extends ImportBatch {
  rows_skipped: number;
  rows: ImportRow[];
  errors: ImportError[];
  warnings: ImportError[];
}

// ---------- 郵件模板（M2-02）----------
export interface EmailTemplate {
  template_id: number;
  family_id: number;
  name: string;
  version: number;
  is_active: boolean;
  subject: string;
  body_text: string;
  created_at: string;
}

export interface TemplateVariable {
  name: string;
  label: string;
  required: boolean;
}

export interface RenderedMail {
  subject: string;
  body_text: string;
  body_html: string;
}

// ---------- 邀請信批次、草稿、寄出（M2-03～M2-07）----------
export type CampaignStatus = "draft" | "generating" | "reviewing" | "scheduled" | "sending" | "done";
export type DraftStatus = "generating" | "pending_review" | "approved" | "discarded" | "sent" | "failed";
export type GenMode = "template_only" | "template_ai" | "full_ai";

export interface CampaignProgress {
  total: number;
  generating: number;
  pending_review: number;
  approved: number;
  scheduled: number;
  sent: number;
  failed: number;
  discarded: number;
}

export interface Campaign {
  campaign_id: number;
  name: string;
  status: CampaignStatus;
  gen_mode: GenMode;
  template_id: number | null;
  template_name: string | null;
  template_version: number | null;
  owner_id: number;
  owner_name: string | null;
  scheduled_at: string | null;
  created_at: string;
  progress: CampaignProgress;
}

export interface CandidateContact {
  contact_id: number;
  name: string | null;
  email: string;
  unsubscribed: boolean;
}

export interface Candidate {
  company_id: number;
  name: string;
  stars: number | null;
  priority: string | null;
  industry: string | null;
  owner_name: string | null;
  contacts: CandidateContact[];
  default_contact_id: number | null;
  reasons: string[];
}

export interface ExcludedCompany {
  company_id: number;
  name: string;
  reasons: string[];
}

export interface CampaignCreated {
  campaign: Campaign;
  job_id: number;
  excluded: ExcludedCompany[];
}

export interface Draft {
  draft_id: number;
  campaign_id: number;
  company_id: number;
  company_name: string;
  contact_id: number;
  contact_name: string | null;
  contact_email: string;
  subject: string;
  body_text: string;
  status: DraftStatus;
  edit_ratio: string | number | null;
  scheduled_at: string | null;
  send_attempts: number;
  last_error: string | null;
  approved_at: string | null;
}

export interface SendResult {
  scheduled: number;
  blocked: { draft_id: number; company_name: string; reasons: string[] }[];
  campaign: Campaign;
}

export interface MailConnection {
  mail_mode: "sandbox" | "live";
  status: "not_required" | "not_connected" | "connected" | "needs_reconnect";
  connected_at: string | null;
  scopes: string[];
  resumed: number;
}

// ---------- 案件追蹤（M3-09～M3-11）----------
export type CaseStatus = "sent" | "tracking" | "replied" | "negotiating" | "no_response" | "won" | "lost";
export type CaseChannel = "email" | "line" | "wechat" | "phone" | "visit" | "other" | "system";
export type CaseResult = "sent" | "replied" | "negotiating" | "won" | "lost" | "no_response";
export type ReminderKind = "overdue_report" | "follow_up_due" | "no_response";

export interface SalesCase {
  case_id: number;
  case_no: string;
  company_id: number;
  company_name: string;
  company_status: CompanyStatus;
  contact_id: number | null;
  contact_name: string | null;
  contact_email: string | null;
  owner_id: number;
  owner_name: string | null;
  origin: "email" | "tracking";
  status: CaseStatus;
  opened_at: string;
  last_update_at: string | null;
  next_follow_up: string | null;
  amount_twd: string | null;
  closed_at: string | null;
  reminders: ReminderKind[];
}

export interface CaseList {
  items: SalesCase[];
  counts: Record<CaseStatus, number>;
}

export interface CaseTimelineItem {
  update_id: number;
  user_name: string | null;
  channel: CaseChannel;
  contact_name: string | null;
  result: CaseResult;
  note: string | null;
  next_follow_up: string | null;
  amount_twd: string | null;
  created_at: string;
}

export interface CaseDetail extends SalesCase {
  timeline: CaseTimelineItem[];
  contacts: { contact_id: number; name: string | null; email: string; unsubscribed: boolean }[];
}

export interface CaseUpdateInput {
  channel: Exclude<CaseChannel, "system">;
  result: Exclude<CaseResult, "sent">;
  note?: string | null;
  next_follow_up?: string | null;
  amount_twd?: number | null;
  contact_id?: number | null;
}

export interface ReminderItem {
  kind: ReminderKind | "pending_review";
  label: string;
  count: number;
}
