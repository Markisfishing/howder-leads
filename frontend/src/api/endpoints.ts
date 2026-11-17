// 每個後端端點一個函式。頁面透過 src/api/hooks.ts 的 React Query hook 使用。
import { api, apiBlob } from "./client";
import type {
  CompanyDetail,
  CompanyPage,
  Dimensions,
  ImportBatch,
  ImportBatchDetail,
  Kpis,
  RejectReason,
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
