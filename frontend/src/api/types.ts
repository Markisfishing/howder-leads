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

export interface Contact {
  contact_id: number;
  name: string | null;
  title: string | null;
  email: string;
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
}

export interface Dimensions {
  industries: { industry_id: number; name: string; is_prospect: boolean }[];
  priorities: { priority: string; label: string; definition: string; suggested_action: string; stars: number }[];
  reject_reasons: RejectReason[];
  statuses: CompanyStatus[];
  users: { user_id: number; display_name: string; role: Role }[];
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
  action: "create" | "update" | "unchanged";
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
}

export interface ImportBatchDetail extends ImportBatch {
  rows: ImportRow[];
  errors: ImportError[];
}
