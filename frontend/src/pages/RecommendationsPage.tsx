import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { downloadCompanies } from "../api/endpoints";
import { useAddTracking, useCompanies, useDimensions, useKpis, useReview } from "../api/hooks";
import type { CompanyRow } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { Button } from "../components/Button";
import { Modal } from "../components/Modal";
import { Empty, ErrorState, InlineError, Loading } from "../components/StateView";
import { type ColumnKey, loadColumns, saveColumns } from "../lib/columns";
import { saveBlob } from "../lib/download";
import { DEFAULT_FILTERS, type ListFilters, parseFilters, toSearchParams, updateFilters } from "../lib/filters";
import { AddCompanyDialog } from "./recommendations/AddCompanyDialog";
import { ColumnPicker } from "./recommendations/ColumnPicker";
import { CompanyDetailPanel } from "./recommendations/CompanyDetailPanel";
import { CompanyList } from "./recommendations/CompanyList";
import { FilterBar } from "./recommendations/FilterBar";
import { RejectDialog } from "./recommendations/RejectDialog";
import { ReviewWorkspace } from "./recommendations/ReviewWorkspace";
import styles from "./recommendations/Recommendations.module.css";

type ViewMode = "review" | "list";

interface Props {
  /** 根路由保留完整清單供既有連結使用；/recommendations 預設進入單筆審核。 */
  initialView?: ViewMode;
}

const SAVED_VIEWS: { label: string; filters: Partial<ListFilters> }[] = [
  { label: "我的待辦", filters: { status: ["pending_review"], owner: "me" } },
  { label: "未指派", filters: { status: ["pending_review"], owner: "none" } },
  { label: "高潛力未聯絡", filters: { status: ["approved"], minStars: 4 } },
  { label: "最近匯入", filters: { sort: "updated" } },
  { label: "團隊已排除", filters: { status: ["rejected"] } },
];

/** 推薦名單：/recommendations 是單筆審核工作台，完整清單保留批次作業與欄位設定。 */
export function RecommendationsPage({ initialView = "list" }: Props) {
  const { isAdmin } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<ViewMode>(initialView);
  const filters = useMemo(() => parseFilters(params), [params]);
  const effectiveFilters = useMemo(
    () => (view === "review" && filters.status.length === 0 ? { ...filters, status: ["pending_review"] } : filters),
    [filters, view],
  );
  const filterKey = toSearchParams(effectiveFilters).toString();
  const openId = Number(params.get("company")) || null;

  const { data, isLoading, isFetching, error, refetch } = useCompanies(effectiveFilters);
  const { data: dimensions } = useDimensions();
  const { data: kpis } = useKpis();
  const review = useReview();
  const tracking = useAddTracking();

  const [selection, setSelection] = useState<{ key: string; ids: Set<number> }>({ key: "", ids: new Set() });
  const selected = selection.key === filterKey ? selection.ids : new Set<number>();
  const setSelected = (ids: Set<number>) => setSelection({ key: filterKey, ids });
  const [reviewIndex, setReviewIndex] = useState(0);
  const [snoozedIds, setSnoozedIds] = useState<Set<number>>(new Set());
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectIds, setRejectIds] = useState<number[]>([]);
  const [filterOpen, setFilterOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [columns, setColumnsState] = useState<ColumnKey[]>(loadColumns);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [exportError, setExportError] = useState<unknown>(null);
  const [exporting, setExporting] = useState(false);
  const [notice, setNoticeState] = useState({ text: "", seq: 0 });
  const noticeRef = useRef<HTMLParagraphElement>(null);
  const rows = useMemo(() => data?.items ?? [], [data?.items]);
  const reviewRows = useMemo(() => rows.filter((row) => !snoozedIds.has(row.company_id)), [rows, snoozedIds]);
  const activeReviewIndex = reviewRows.length === 0 ? 0 : Math.min(reviewIndex, reviewRows.length - 1);
  useEffect(() => {
    if (notice.text) noticeRef.current?.focus();
  }, [notice]);

  const setNotice = useCallback((text: string) => setNoticeState((n) => ({ text, seq: n.seq + 1 })), []);
  const setColumns = (next: ColumnKey[]) => {
    setColumnsState(next);
    saveColumns(next);
  };
  const writeParams = useCallback(
    (next: ListFilters, company: number | null) => {
      const nextParams = toSearchParams(next);
      if (company) nextParams.set("company", String(company));
      setParams(nextParams);
    },
    [setParams],
  );
  const onFilterChange = useCallback(
    (patch: Partial<ListFilters>) => writeParams(updateFilters(filters, patch), openId),
    [filters, openId, writeParams],
  );
  const openCompany = (id: number | null) => writeParams(filters, id);

  const approveCompany = useCallback(
    (company: CompanyRow) => {
      review.mutate(
        { company_ids: [company.company_id], decision: "approved" },
        { onSuccess: () => { setReviewIndex(0); setNotice(`已通過${company.name}・復原`); } },
      );
    },
    [review, setNotice],
  );
  const snoozeCompany = useCallback(
    (company: CompanyRow) => {
      setSnoozedIds((current) => new Set(current).add(company.company_id));
      setReviewIndex(0);
      setNotice(`已將${company.name}放到稍後，今日仍可繼續審核`);
    },
    [setNotice],
  );
  const openReject = useCallback((company: CompanyRow) => {
    setRejectIds([company.company_id]);
    setRejectOpen(true);
  }, []);

  const toggle = (id: number) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };
  const toggleAll = (checked: boolean) => setSelected(checked ? new Set(rows.map((row) => row.company_id)) : new Set());
  const approveSelected = () => {
    review.mutate(
      { company_ids: [...selected], decision: "approved" },
      { onSuccess: (res) => { setNotice(`已通過 ${res.updated} 家公司`); setSelected(new Set()); } },
    );
  };
  const trackSelected = () => {
    tracking.mutate([...selected], {
      onSuccess: (cases) => { setNotice(`已加入追蹤 ${cases.length} 家，請到「案件」回填聯絡結果`); setSelected(new Set()); },
    });
  };
  const doExport = async () => {
    setExportError(null);
    setExporting(true);
    try { saveBlob(await downloadCompanies(filters, columns), "companies"); }
    catch (err) { setExportError(err); }
    finally { setExporting(false); }
  };

  const activeFilterCount = [
    filters.q, filters.stars.length, filters.industryId, filters.owner, filters.hasWebsite, filters.competitor,
    filters.country, filters.source, filters.urlStatus, filters.productType, filters.tag, filters.minStars, filters.status.length,
  ].filter(Boolean).length;
  const industryName = dimensions?.industries.find((item) => item.industry_id === filters.industryId)?.name;
  const ownerName = filters.owner === "me" ? "我負責" : filters.owner === "none" ? "未指派" : dimensions?.users.find((item) => String(item.user_id) === filters.owner)?.display_name;
  const filterChips = [
    ...(filters.stars.length ? [{ label: `${filters.stars.join("、")} 星`, patch: { stars: [] } }] : []),
    ...(industryName ? [{ label: industryName, patch: { industryId: null } }] : []),
    ...(ownerName ? [{ label: ownerName, patch: { owner: null } }] : []),
    ...(filters.source ? [{ label: `來源：${filters.source}`, patch: { source: null } }] : []),
    ...(filters.country ? [{ label: filters.country, patch: { country: null } }] : []),
    ...(filters.status.length ? [{ label: filters.status.map((status) => status === "pending_review" ? "待審" : status).join("、"), patch: { status: [] } }] : []),
  ];
  const applySavedView = (saved: Partial<ListFilters>) => {
    setView("list");
    writeParams({ ...DEFAULT_FILTERS, ...saved }, null);
  };
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <>
      <header className={styles.head}>
        <div>
          <div className={styles.titleLine}>
            <h1 className={styles.title}>{view === "review" ? "今日審核" : "推薦名單"}</h1>
            <div className={styles.modeSwitch} aria-label="檢視模式">
              <button type="button" className={view === "review" ? styles.modeActive : styles.modeButton} onClick={() => setView("review")}>審核模式</button>
              <button type="button" className={view === "list" ? styles.modeActive : styles.modeButton} onClick={() => setView("list")}>完整清單</button>
            </div>
          </div>
          <p className={styles.meta}>{view === "review" ? "一次判斷一家公司，完成今日待審名單" : "比較、分派與批次處理推薦公司"}</p>
        </div>
        <div className={styles.headActions}>
          <Button onClick={() => setFilterOpen(true)}>篩選{activeFilterCount > 0 && ` ${activeFilterCount}`}</Button>
          {view === "list" && <>
            <Button onClick={() => setPickerOpen(true)}>欄位設定</Button>
            <Button busy={exporting} onClick={() => void doExport()}>匯出 CSV</Button>
            <Button onClick={() => setAddOpen(true)}>＋手動加入</Button>
            {isAdmin && <Button variant="primary" onClick={() => navigate("/admin/imports")}>匯入名單</Button>}
          </>}
        </div>
      </header>

      {view === "list" && <nav className={styles.savedViews} aria-label="已儲存檢視">
        {SAVED_VIEWS.map((saved) => <button key={saved.label} type="button" className={styles.savedView} onClick={() => applySavedView(saved.filters)}>{saved.label}</button>)}
      </nav>}

      <div className={styles.filterSummary}>
        <span className={styles.filterSummaryLabel}>{view === "review" ? "生效條件" : `顯示 ${data?.total ?? "…"} 筆`}</span>
        {view === "review" && filters.status.length === 0 && <span className={styles.filterChip}>待審</span>}
        {filterChips.map((chip) => <button key={chip.label} type="button" className={styles.filterChip} onClick={() => onFilterChange(chip.patch)}>{chip.label} ×</button>)}
        {filterChips.length === 0 && view === "list" && <span className={styles.filterEmpty}>未套用額外篩選</span>}
      </div>

      <InlineError error={exportError} />
      <div aria-live="polite">{notice.text && <p ref={noticeRef} tabIndex={-1} className={styles.notice}>{notice.text}</p>}</div>

      {view === "review" ? <>
        <div className={styles.reviewProgress}>
          <span>今日進度</span>
          <strong>{kpis ? `${Math.max(0, (data?.total ?? kpis.pending_review) - reviewRows.length)} / ${data?.total ?? kpis.pending_review}` : "…"}</strong>
          <span className={styles.progressHint}>待審 {reviewRows.length} · 稍後 {snoozedIds.size}</span>
        </div>
        {isLoading ? <Loading /> : error ? <ErrorState error={error} onRetry={() => void refetch()} /> : <ReviewWorkspace key={reviewRows[activeReviewIndex]?.company_id ?? "empty"} rows={reviewRows} currentIndex={activeReviewIndex} onIndexChange={setReviewIndex} onApprove={approveCompany} onReject={openReject} onSnooze={snoozeCompany} onOpenDetails={(company) => openCompany(company.company_id)} busy={review.isPending} />}
      </> : <>
        {isLoading ? <Loading /> : error ? <ErrorState error={error} onRetry={() => void refetch()} /> : rows.length === 0 ? <Empty title="沒有符合條件的公司">{activeFilterCount > 0 ? "試著放寬篩選條件。" : "還沒有匯入名單，請管理員到「名單匯入」上傳。"}</Empty> : <>
          <CompanyList rows={rows} selected={selected} onToggle={toggle} onToggleAll={toggleAll} onOpen={openCompany} columns={columns} />
          <nav className={styles.pager} aria-label="分頁"><span className={styles.pagerInfo}>共 {data?.total ?? 0} 家，第 {filters.page} / {totalPages} 頁{isFetching && "（更新中…）"}</span><span className={styles.pagerButtons}><Button size="sm" disabled={filters.page <= 1} onClick={() => onFilterChange({ page: filters.page - 1 })}>上一頁</Button><Button size="sm" disabled={filters.page >= totalPages} onClick={() => onFilterChange({ page: filters.page + 1 })}>下一頁</Button></span></nav>
        </>}
        {selected.size > 0 && <div className={styles.bulkbar} role="region" aria-label="批次操作"><span className={styles.bulkCount}>已選 {selected.size} 家</span><InlineError error={review.error ?? tracking.error} /><span className={styles.bulkActions}><Button onClick={() => setSelected(new Set())}>取消選取</Button><Button busy={tracking.isPending} onClick={trackSelected}>加入追蹤</Button><Button variant="danger" onClick={() => { setRejectIds([...selected]); setRejectOpen(true); }}>排除…</Button><Button variant="primary" busy={review.isPending} onClick={approveSelected}>通過</Button></span></div>}
      </>}

      <Modal open={filterOpen} onOpenChange={setFilterOpen} title="篩選推薦名單" variant="side" footer={<Button variant="primary" onClick={() => setFilterOpen(false)}>完成</Button>}><FilterBar filters={filters} onChange={onFilterChange} /></Modal>
      <RejectDialog open={rejectOpen} companyIds={rejectIds} onClose={() => setRejectOpen(false)} onDone={(count) => { setRejectOpen(false); setReviewIndex(0); setSelected(new Set()); setNotice(`已排除 ${count} 家公司`); }} />
      <ColumnPicker open={pickerOpen} columns={columns} onChange={setColumns} onClose={() => setPickerOpen(false)} />
      <AddCompanyDialog open={addOpen} onClose={() => setAddOpen(false)} onCreated={(id) => { setNotice("已加入，請審核"); openCompany(id); }} />
      <Modal open={openId !== null} onOpenChange={(open) => !open && openCompany(null)} title="公司詳情" variant="side">{openId !== null && <CompanyDetailPanel companyId={openId} showPageLink />}</Modal>
    </>
  );
}
