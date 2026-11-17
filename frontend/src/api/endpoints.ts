// 每個後端端點一個函式。頁面透過 src/api/hooks.ts 的 React Query hook 使用。
import { api, apiBlob } from "./client";
import type {
  CompanyDetail,
  CompanyPage,
  Contact,
  ContactSource,
  Dimensions,
  EmailTemplate,
  ImportBatch,
  ImportBatchDetail,
  Kpis,
  RejectReason,
  RenderedMail,
  TemplateVariable,
  User,
} from "./types";
import type { ListFilters } from "../lib/filters";

export const getMe = () => api<User>("/me");

export const listCompanies = (f: ListFilters) =>
  api<CompanyPage>("/companies", {
    query: {
      stars: f.stars,
      status: f.status,
      industry_id: f.industryId,
      owner: f.owner,
      has_website: f.hasWebsite,
      competitor: f.competitor,
      q: f.q,
      sort: f.sort,
      page: f.page,
      page_size: f.pageSize,
    },
  });

export const getCompany = (id: number) => api<CompanyDetail>(`/companies/${id}`);

export interface CompanyPatch {
  website_url?: string;
  clear_website?: boolean;
  industry_id?: number;
  note?: string;
}
export const patchCompany = (id: number, body: CompanyPatch) =>
  api<CompanyDetail>(`/companies/${id}`, { method: "PATCH", json: body });

export interface CompanyCreate {
  tax_id: string;
  name: string;
  website_url?: string;
  industry_id?: number;
  note?: string;
}
export const createCompany = (body: CompanyCreate) =>
  api<CompanyDetail>("/companies", { method: "POST", json: body });

// ---------- 聯絡人（M2-01）----------
export interface ContactCreate {
  company_id: number;
  email: string;
  source: ContactSource;
  name?: string;
  title?: string;
  is_verified?: boolean;
}
export const createContact = (body: ContactCreate) => api<Contact>("/contacts", { method: "POST", json: body });

/** 只送有改的欄位；name、title 送 null 代表清空 */
export interface ContactPatch {
  email?: string;
  source?: ContactSource;
  name?: string | null;
  title?: string | null;
  is_verified?: boolean;
}
export const patchContact = (id: number, body: ContactPatch) =>
  api<Contact>(`/contacts/${id}`, { method: "PATCH", json: body });
export const unsubscribeContact = (id: number, note?: string) =>
  api<Contact>(`/contacts/${id}/unsubscribe`, { method: "POST", json: { note } });
/** 個資刪除：主管／管理員，一定要填原因 */
export const deleteContact = (id: number, reason: string) =>
  api<void>(`/contacts/${id}`, { method: "DELETE", json: { reason } });

export const claimCompany = (id: number) => api<CompanyDetail>(`/companies/${id}/claim`, { method: "POST" });
export const releaseCompany = (id: number) => api<CompanyDetail>(`/companies/${id}/release`, { method: "POST" });

export interface ReviewBody {
  company_ids: number[];
  decision: "approved" | "rejected";
  reject_reason?: RejectReason;
  note?: string;
  corrected_industry_id?: number;
}
export const submitReview = (body: ReviewBody) =>
  api<{ updated: number; status: string }>("/reviews", { method: "POST", json: body });

export const getKpis = () => api<Kpis>("/metrics/kpis");
export const getDimensions = () => api<Dimensions>("/dimensions");

export const uploadImport = (file: File, modelName?: string) => {
  const form = new FormData();
  form.append("file", file);
  if (modelName) form.append("model_name", modelName);
  return api<ImportBatchDetail>("/imports", { method: "POST", form });
};
export const listImports = () => api<ImportBatch[]>("/imports");
export const getImport = (id: number) => api<ImportBatchDetail>(`/imports/${id}`);
export const commitImport = (id: number) => api<ImportBatchDetail>(`/imports/${id}/commit`, { method: "POST" });
export const cancelImport = (id: number) => api<ImportBatchDetail>(`/imports/${id}/cancel`, { method: "POST" });
export const downloadReviewExport = () => apiBlob("/admin/reviews/export");

// ---------- 郵件模板（M2-02）----------
export interface TemplateBody {
  name: string;
  subject: string;
  body_text: string;
}
export const listTemplates = () => api<EmailTemplate[]>("/templates");
export const listTemplateVariables = () => api<TemplateVariable[]>("/templates/variables");
export const templateVersions = (id: number) => api<EmailTemplate[]>(`/templates/${id}/versions`);
export const createTemplate = (body: TemplateBody) =>
  api<EmailTemplate>("/templates", { method: "POST", json: body });
/** 修改會新增一個版本，舊版保留 */
export const updateTemplate = (id: number, body: TemplateBody) =>
  api<EmailTemplate>(`/templates/${id}`, { method: "PUT", json: body });
export const archiveTemplate = (id: number) => api<EmailTemplate>(`/templates/${id}/archive`, { method: "POST" });
export const previewTemplate = (body: Omit<TemplateBody, "name">) =>
  api<RenderedMail>("/templates/preview", { method: "POST", json: body });
