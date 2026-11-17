import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { downloadCompanies } from "../api/endpoints";
import { useAddTracking, useCompanies, useReview } from "../api/hooks";
import { useAuth } from "../auth/AuthProvider";
import { Button } from "../components/Button";
import { Modal } from "../components/Modal";
import { Empty, ErrorState, InlineError, Loading } from "../components/StateView";
import { type ColumnKey, loadColumns, saveColumns } from "../lib/columns";
import { saveBlob } from "../lib/download";
import { type ListFilters, parseFilters, toSearchParams, updateFilters } from "../lib/filters";
import { AddCompanyDialog } from "./recommendations/AddCompanyDialog";
import { ColumnPicker } from "./recommendations/ColumnPicker";
import { CompanyDetailPanel } from "./recommendations/CompanyDetailPanel";
import { CompanyList } from "./recommendations/CompanyList";
import { FilterBar } from "./recommendations/FilterBar";
import { KpiCards } from "./recommendations/KpiCards";
import { RejectDialog } from "./recommendations/RejectDialog";
import styles from "./recommendations/Recommendations.module.css";

/** 推薦清單頁（SPEC 6.2 /）：KPI → 篩選 → 清單 → 批次審核；點公司名稱從右側開詳情 */
export function RecommendationsPage() {
  const { isAdmin } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => parseFilters(params), [params]);
  const filterKey = toSearchParams(filters).toString();
  const openId = Number(params.get("company")) || null;

  const { data, isLoading, isFetching, error, refetch } = useCompanies(filters);
  const review = useReview();
  const tracking = useAddTracking();

  // 勾選跟著目前的篩選條件；條件一變，勾選自動清空，避免對看不到的公司做批次操作
  const [selection, setSelection] = useState<{ key: string; ids: Set<number> }>({ key: "", ids: new Set() });
  const selected = selection.key === filterKey ? selection.ids : new Set<number>();
  const setSelected = (ids: Set<number>) => setSelection({ key: filterKey, ids });

  const [rejectOpen, setRejectOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  // 欄位自選（M3-13b、F-REC-8）：記在這台瀏覽器
  const [columns, setColumnsState] = useState<ColumnKey[]>(loadColumns);
  const [pickerOpen, setPickerOpen] = useState(false);
  const setColumns = (cols: ColumnKey[]) => {
    setColumnsState(cols);
    saveColumns(cols);
  };
  const [exportError, setExportError] = useState<unknown>(null);
  const [exporting, setExporting] = useState(false);
  const doExport = async () => {
    setExportError(null);
    setExporting(true);
    try {
      saveBlob(await downloadCompanies(filters, columns), "companies");
    } catch (err) {
      setExportError(err);
    } finally {
      setExporting(false);
    }
  };
  const [notice, setNoticeState] = useState({ text: "", seq: 0 });
  const setNotice = (text: string) => setNoticeState((n) => ({ text, seq: n.seq + 1 }));
  // 批次操作完成後批次列會消失，把焦點移到結果訊息，鍵盤使用者才不會掉回頁首
  const noticeRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (notice.text) noticeRef.current?.focus();
  }, [notice]);

  const writeParams = useCallback(
    (next: ListFilters, company: number | null) => {
      const p = toSearchParams(next);
      if (company) p.set("company", String(company));
      setParams(p);
    },
    [setParams],
  );

  const onFilterChange = useCallback(
    (patch: Partial<ListFilters>) => writeParams(updateFilters(filters, patch), openId),
    [filters, openId, writeParams],
  );
  const openCompany = (id: number | null) => writeParams(filters, id);

  const rows = data?.items ?? [];
  const toggle = (id: number) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };
  const toggleAll = (checked: boolean) => setSelected(checked ? new Set(rows.map((r) => r.company_id)) : new Set());

  const approveSelected = () => {
    setNotice("");
    review.mutate(
      { company_ids: [...selected], decision: "approved" },
      {
        onSuccess: (res) => {
          setNotice(`已通過 ${res.updated} 家公司`);
          setSelected(new Set());
        },
      },
    );
  };

  // F-REC-9：不寄信也能直接開案（先打電話、拜訪），之後在案件頁回填
  const trackSelected = () => {
    setNotice("");
    tracking.mutate([...selected], {
      onSuccess: (cases) => {
        setNotice(`已加入追蹤 ${cases.length} 家，請到「案件」回填聯絡結果`);
        setSelected(new Set());
      },
    });
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <>
      {/* 區塊：頁首 */}
      <header className={styles.head}>
        <div>
          <h1 className={styles.title}>推薦清單</h1>
          <p className={styles.meta}>依推薦度排序，勾選後可以批次通過或排除</p>
        </div>
        <div className={styles.headActions}>
          <Button onClick={() => setPickerOpen(true)}>顯示欄位</Button>
          <Button busy={exporting} onClick={() => void doExport()}>
            匯出 CSV
          </Button>
          <Button onClick={() => setAddOpen(true)}>手動加入</Button>
          {isAdmin && (
            <Button variant="primary" onClick={() => navigate("/admin/imports")}>
              匯入名單
            </Button>
          )}
        </div>
      </header>

      <InlineError error={exportError} />
      <KpiCards />
      <FilterBar filters={filters} onChange={onFilterChange} />

      <div aria-live="polite">
        {notice.text && (
          <p ref={noticeRef} tabIndex={-1} className={styles.notice}>
            {notice.text}
          </p>
        )}
      </div>

      {/* 區塊：清單（四種狀態） */}
      {isLoading ? (
        <Loading />
      ) : error ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : rows.length === 0 ? (
        <Empty title="沒有符合條件的公司">
          {filterKey ? "試著放寬篩選條件。" : "還沒有匯入名單，請管理員到「名單匯入」上傳。"}
        </Empty>
      ) : (
        <>
          <CompanyList
            rows={rows}
            selected={selected}
            onToggle={toggle}
            onToggleAll={toggleAll}
            onOpen={(id) => openCompany(id)}
            columns={columns}
          />
          <nav className={styles.pager} aria-label="分頁">
            <span className={styles.pagerInfo}>
              共 {data?.total ?? 0} 家，第 {filters.page} / {totalPages} 頁{isFetching && "（更新中…）"}
            </span>
            <span className={styles.pagerButtons}>
              <Button size="sm" disabled={filters.page <= 1} onClick={() => onFilterChange({ page: filters.page - 1 })}>
                上一頁
              </Button>
              <Button
                size="sm"
                disabled={filters.page >= totalPages}
                onClick={() => onFilterChange({ page: filters.page + 1 })}
              >
                下一頁
              </Button>
            </span>
          </nav>
        </>
      )}

      {/* 區塊：批次動作列 · 有勾選才出現 */}
      {selected.size > 0 && (
        <div className={styles.bulkbar} role="region" aria-label="批次操作">
          <span className={styles.bulkCount}>已選 {selected.size} 家</span>
          <InlineError error={review.error ?? tracking.error} />
          <span className={styles.bulkActions}>
            <Button onClick={() => setSelected(new Set())}>取消選取</Button>
            <Button busy={tracking.isPending} onClick={trackSelected}>
              加入追蹤
            </Button>
            <Button variant="danger" onClick={() => setRejectOpen(true)}>
              排除…
            </Button>
            <Button variant="primary" busy={review.isPending} onClick={approveSelected}>
              通過
            </Button>
          </span>
        </div>
      )}

      <RejectDialog
        open={rejectOpen}
        companyIds={[...selected]}
        onClose={() => setRejectOpen(false)}
        onDone={(n) => {
          setNotice(`已排除 ${n} 家公司`);
          setSelected(new Set());
        }}
      />
      <ColumnPicker
        open={pickerOpen}
        columns={columns}
        onChange={setColumns}
        onClose={() => setPickerOpen(false)}
      />
      <AddCompanyDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onCreated={(id) => {
          setNotice("已加入，請審核");
          openCompany(id);
        }}
      />

      {/* 區塊：公司詳情側欄 · 網址帶 ?company=id，重新整理或分享都會停在同一家 */}
      <Modal open={openId !== null} onOpenChange={(o) => !o && openCompany(null)} title="公司詳情" variant="side">
        {openId !== null && <CompanyDetailPanel companyId={openId} showPageLink />}
      </Modal>
    </>
  );
}
