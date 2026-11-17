// React Query hook：資料快取與重新整理的規則集中在這裡
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as ep from "./endpoints";
import type { ListFilters } from "../lib/filters";

export const keys = {
  me: ["me"] as const,
  companies: (f: ListFilters) => ["companies", f] as const,
  company: (id: number) => ["company", id] as const,
  kpis: ["kpis"] as const,
  dimensions: ["dimensions"] as const,
  imports: ["imports"] as const,
  importBatch: (id: number) => ["imports", id] as const,
};

export const useCompanies = (f: ListFilters) =>
  useQuery({ queryKey: keys.companies(f), queryFn: () => ep.listCompanies(f), placeholderData: keepPreviousData });

export const useCompany = (id: number | null) =>
  useQuery({ queryKey: keys.company(id ?? 0), queryFn: () => ep.getCompany(id!), enabled: id !== null });

export const useKpis = () => useQuery({ queryKey: keys.kpis, queryFn: ep.getKpis });

export const useDimensions = () =>
  useQuery({ queryKey: keys.dimensions, queryFn: ep.getDimensions, staleTime: 10 * 60 * 1000 });

export const useImports = () => useQuery({ queryKey: keys.imports, queryFn: ep.listImports });

/** 會改到公司資料的操作，成功後讓清單、詳情、KPI 重新抓。 */
function useCompanyMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["companies"] });
      void qc.invalidateQueries({ queryKey: ["company"] });
      void qc.invalidateQueries({ queryKey: keys.kpis });
    },
  });
}

export const useReview = () => useCompanyMutation(ep.submitReview);
export const usePatchCompany = () =>
  useCompanyMutation(({ id, body }: { id: number; body: ep.CompanyPatch }) => ep.patchCompany(id, body));
export const useCreateCompany = () => useCompanyMutation(ep.createCompany);
export const useClaim = () => useCompanyMutation(ep.claimCompany);
export const useRelease = () => useCompanyMutation(ep.releaseCompany);

// 聯絡人改動也會影響公司（退訂會變成「不再聯絡」），所以一樣重新抓清單、詳情、KPI
export const useCreateContact = () => useCompanyMutation(ep.createContact);
export const usePatchContact = () =>
  useCompanyMutation(({ id, body }: { id: number; body: ep.ContactPatch }) => ep.patchContact(id, body));
export const useUnsubscribeContact = () =>
  useCompanyMutation(({ id, note }: { id: number; note?: string }) => ep.unsubscribeContact(id, note));
export const useDeleteContact = () =>
  useCompanyMutation(({ id, reason }: { id: number; reason: string }) => ep.deleteContact(id, reason));

export function useImportActions() {
  const qc = useQueryClient();
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: keys.imports });
    void qc.invalidateQueries({ queryKey: ["companies"] });
    void qc.invalidateQueries({ queryKey: keys.kpis });
  };
  return {
    upload: useMutation({
      mutationFn: ({ file, modelName }: { file: File; modelName?: string }) => ep.uploadImport(file, modelName),
      onSuccess: refresh,
    }),
    commit: useMutation({ mutationFn: ep.commitImport, onSuccess: refresh }),
    cancel: useMutation({ mutationFn: ep.cancelImport, onSuccess: refresh }),
    /** 從匯入紀錄重新打開還在預覽中的批次 */
    open: useMutation({ mutationFn: ep.getImport }),
  };
}
