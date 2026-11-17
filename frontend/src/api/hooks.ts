// React Query hook：資料快取與重新整理的規則集中在這裡
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as ep from "./endpoints";
import type { Campaign, CaseUpdateInput } from "./types";
import type { ListFilters } from "../lib/filters";

export const keys = {
  me: ["me"] as const,
  companies: (f: ListFilters) => ["companies", f] as const,
  company: (id: number) => ["company", id] as const,
  kpis: ["kpis"] as const,
  dimensions: ["dimensions"] as const,
  imports: ["imports"] as const,
  importBatch: (id: number) => ["imports", id] as const,
  templates: ["templates"] as const,
  templateVersions: (id: number) => ["templates", id, "versions"] as const,
  templateVariables: ["templateVariables"] as const,
  campaigns: ["campaigns"] as const,
  campaign: (id: number) => ["campaigns", id] as const,
  drafts: (id: number) => ["campaigns", id, "drafts"] as const,
  candidates: ["candidates"] as const,
  exclusionReasons: ["exclusionReasons"] as const,
  mailConnection: ["mailConnection"] as const,
  cases: (q: object) => ["cases", q] as const,
  case: (id: number) => ["case", id] as const,
  reminders: ["reminders"] as const,
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

// ---------- 郵件模板（M2-02）----------
export const useTemplates = () => useQuery({ queryKey: keys.templates, queryFn: ep.listTemplates });
export const useTemplateVariables = () =>
  useQuery({ queryKey: keys.templateVariables, queryFn: ep.listTemplateVariables, staleTime: Infinity });
export const useTemplateVersions = (id: number | null) =>
  useQuery({ queryKey: keys.templateVersions(id ?? 0), queryFn: () => ep.templateVersions(id!), enabled: id !== null });

/** 用假資料預覽；頁面先用 useDebounced 把輸入延遲，避免每打一個字就呼叫一次 */
export const useTemplatePreview = (subject: string, bodyText: string) =>
  useQuery({
    queryKey: ["templatePreview", subject, bodyText],
    queryFn: () => ep.previewTemplate({ subject, body_text: bodyText }),
    enabled: subject.trim() !== "" && bodyText.trim() !== "",
    retry: false,
    placeholderData: keepPreviousData,
  });

export function useTemplateActions() {
  const qc = useQueryClient();
  const refresh = () => void qc.invalidateQueries({ queryKey: keys.templates });
  return {
    create: useMutation({ mutationFn: ep.createTemplate, onSuccess: refresh }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: ep.TemplateBody }) => ep.updateTemplate(id, body),
      onSuccess: refresh,
    }),
    archive: useMutation({ mutationFn: ep.archiveTemplate, onSuccess: refresh }),
  };
}

// ---------- 邀請信批次、草稿、寄出（M2-03～M2-07）----------
/** 產生中或排程寄送中，每 2 秒更新一次進度（F-MAIL-3） */
export const isBusy = (c: Campaign | undefined) =>
  !!c && (c.status === "generating" || c.status === "scheduled" || c.status === "sending");

export const useCampaigns = () => useQuery({ queryKey: keys.campaigns, queryFn: ep.listCampaigns });
export const useCampaign = (id: number) =>
  useQuery({
    queryKey: keys.campaign(id),
    queryFn: () => ep.getCampaign(id),
    refetchInterval: (q) => (isBusy(q.state.data) ? 2000 : false),
  });
export const useDrafts = (id: number, poll: boolean) =>
  useQuery({ queryKey: keys.drafts(id), queryFn: () => ep.listDrafts(id), refetchInterval: poll ? 2000 : false });
export const useCandidates = () => useQuery({ queryKey: keys.candidates, queryFn: ep.listCandidates });
export const useExclusionReasons = () =>
  useQuery({ queryKey: keys.exclusionReasons, queryFn: ep.getExclusionReasons, staleTime: Infinity });
export const useMailConnection = () => useQuery({ queryKey: keys.mailConnection, queryFn: ep.getMailConnection });

/** 會改到批次、草稿、公司狀態的操作：成功後相關資料都重新抓 */
function useMailMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.campaigns });
      void qc.invalidateQueries({ queryKey: keys.candidates });
      void qc.invalidateQueries({ queryKey: ["companies"] });
      void qc.invalidateQueries({ queryKey: ["company"] });
      void qc.invalidateQueries({ queryKey: keys.kpis });
    },
  });
}

export const useCreateCampaign = () => useMailMutation(ep.createCampaign);
export const useApproveAll = () => useMailMutation(ep.approveAll);
export const useSendCampaign = () =>
  useMailMutation(({ id, scheduledAt }: { id: number; scheduledAt?: string }) => ep.sendCampaign(id, scheduledAt));
export const usePatchDraft = () =>
  useMailMutation(({ id, body }: { id: number; body: { subject?: string; body_text?: string } }) =>
    ep.patchDraft(id, body),
  );
export const useApproveDraft = () => useMailMutation(ep.approveDraft);
export const useUnapproveDraft = () => useMailMutation(ep.unapproveDraft);
export const useDiscardDraft = () => useMailMutation(ep.discardDraft);
export const useRegenerateDraft = () => useMailMutation(ep.regenerateDraft);

export function useMailConnectionActions() {
  const qc = useQueryClient();
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: keys.mailConnection });
    void qc.invalidateQueries({ queryKey: keys.campaigns });
  };
  return {
    connect: useMutation({ mutationFn: ep.connectMail, onSuccess: refresh }),
    disconnect: useMutation({ mutationFn: ep.disconnectMail, onSuccess: refresh }),
  };
}

// ---------- 案件追蹤（M3-09～M3-11）----------
export const useCases = (q: ep.CaseQuery) =>
  useQuery({ queryKey: keys.cases(q), queryFn: () => ep.listCases(q), placeholderData: keepPreviousData });
export const useCase = (id: number) => useQuery({ queryKey: keys.case(id), queryFn: () => ep.getCase(id) });
export const useReminders = () => useQuery({ queryKey: keys.reminders, queryFn: ep.getReminders });

/** 案件變動會影響：案件列表、提醒、公司狀態、KPI、總覽 */
function useCaseMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      for (const key of [["cases"], ["case"], keys.reminders, ["companies"], ["company"], keys.kpis, ["overview"]])
        void qc.invalidateQueries({ queryKey: key });
    },
  });
}
export const useAddCaseUpdate = () =>
  useCaseMutation(({ id, body }: { id: number; body: CaseUpdateInput }) => ep.addCaseUpdate(id, body));
export const useUnsubscribeCase = () =>
  useCaseMutation(({ id, contactId }: { id: number; contactId?: number | null }) => ep.unsubscribeCase(id, contactId));
export const useAddTracking = () => useCaseMutation(ep.addTracking);
