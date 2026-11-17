import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { downloadCases, type CaseQuery } from "../../api/endpoints";
import { useCases, useDimensions } from "../../api/hooks";
import type { CaseStatus } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { Button } from "../../components/Button";
import { Modal } from "../../components/Modal";
import { Empty, ErrorState, InlineError, Loading } from "../../components/StateView";
import { Tag } from "../../components/Tag";
import { saveBlob } from "../../lib/download";
import { CASE_STATUS_LABELS, CASE_STATUS_TONE, formatDate } from "../../lib/labels";
import styles from "../Page.module.css";
import { CaseDetailPage } from "./CasePanel";
import c from "./Cases.module.css";

const STATUSES = Object.keys(CASE_STATUS_LABELS) as CaseStatus[];
export type CaseQueue = "todo" | "overdue" | "follow_up" | "all";

/** 網址參數 ⇄ 案件篩選（F-CASE-4：篩選反映在網址上，可以分享） */
export function readCaseQuery(sp: URLSearchParams): CaseQuery {
  const status = sp.get("status");
  const owner = Number(sp.get("owner"));
  const queue = sp.get("queue");
  const page = Number(sp.get("page"));
  return {
    q: sp.get("q") || null,
    queue: queue && ["todo", "overdue", "follow_up", "all"].includes(queue) ? (queue as CaseQueue) : null,
    status: status && (STATUSES as string[]).includes(status) ? status : null,
    owner: Number.isInteger(owner) && owner > 0 ? owner : null,
    sent_from: sp.get("from") || null,
    sent_to: sp.get("to") || null,
    overdue: sp.get("overdue") === "1",
    page: Number.isInteger(page) && page > 0 ? page : 1,
    page_size: 30,
  };
}

/** 案件工作佇列（/cases）。清單與詳情刻意分成兩個任務頁。 */
export function CasesPage() {
  const selected = Number(useParams().id) || null;
  return selected ? <CaseDetailPage /> : <CasesQueuePage />;
}

function CasesQueuePage() {
  const [sp, setSp] = useSearchParams();
  const rawQuery = readCaseQuery(sp);
  const { isManager } = useAuth();
  const effectiveQueue = rawQuery.queue ?? "todo";
  const query: CaseQuery = { ...rawQuery, queue: effectiveQueue };
  const { data, isLoading, error, refetch } = useCases(query);
  const dims = useDimensions();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [exportError, setExportError] = useState<unknown>(null);
  const search = sp.toString() ? `?${sp.toString()}` : "";

  const setParam = (key: string, value: string | null, resetPage = true) => {
    const next = new URLSearchParams(sp);
    if (value) next.set(key, value);
    else next.delete(key);
    if (resetPage && key !== "page") next.delete("page");
    setSp(next, { replace: true });
  };

  const resetFilters = () => {
    const next = new URLSearchParams();
    next.set("queue", effectiveQueue);
    setSp(next, { replace: true });
  };

  const doExport = async () => {
    setExportError(null);
    try {
      saveBlob(await downloadCases(query), "cases");
      setMenuOpen(false);
    } catch (err) {
      setExportError(err);
    }
  };

  const queueCounts = data?.queue_counts ?? { todo: data?.items.length ?? 0, overdue: 0, follow_up: 0, all: data?.items.length ?? 0 };
  const total = data?.total ?? data?.items.length ?? 0;
  const page = data?.page ?? rawQuery.page ?? 1;
  const pageSize = data?.page_size ?? 30;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const activeFilterCount = [rawQuery.status, rawQuery.sent_from, rawQuery.sent_to, rawQuery.overdue ? "overdue" : null]
    .filter(Boolean).length;

  return (
    <main className={c.queuePage}>
      <header className={styles.head}>
        <div className={c.headRow}>
          <div><h1 className={styles.title}>案件</h1><p className={styles.meta}>集中處理今天需要跟進的案件。</p></div>
          <div className={c.headActions}>
            <Button size="sm" aria-label="案件說明" title="案件說明" onClick={() => setHelpOpen(true)}>?</Button>
            <div className={c.moreMenu}>
              <Button size="sm" aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}>⋯</Button>
              {menuOpen && <div className={c.menu} role="menu"><button type="button" role="menuitem" onClick={() => void doExport()}>匯出 CSV</button></div>}
            </div>
          </div>
        </div>
        <InlineError error={exportError} />
      </header>

      <nav className={c.queueTabs} aria-label="案件工作佇列">
        <QueueTab active={effectiveQueue === "todo"} count={queueCounts.todo} onClick={() => setParam("queue", "todo")}>{isManager ? "團隊待辦" : "我的待辦"}</QueueTab>
        <QueueTab active={effectiveQueue === "overdue"} count={queueCounts.overdue} onClick={() => setParam("queue", "overdue")}>逾期</QueueTab>
        <QueueTab active={effectiveQueue === "follow_up"} count={queueCounts.follow_up} onClick={() => setParam("queue", "follow_up")}>待追蹤</QueueTab>
        <QueueTab active={effectiveQueue === "all"} count={queueCounts.all} onClick={() => setParam("queue", "all")}>全部案件</QueueTab>
      </nav>

      <section className={c.toolbar} aria-label="案件搜尋與篩選">
        <label className={c.searchField}><span className="visually-hidden">搜尋公司或案件編號</span><span aria-hidden="true">⌕</span>
          <input value={rawQuery.q ?? ""} onChange={(event) => setParam("q", event.target.value || null)} placeholder="搜尋公司或案件編號" type="search" />
        </label>
        {isManager && <label className={c.compactField}><span className="visually-hidden">負責人</span>
          <select value={rawQuery.owner ?? ""} onChange={(event) => setParam("owner", event.target.value || null)}>
            <option value="">負責人：全部</option>
            {dims.data?.users.map((user) => <option key={user.user_id} value={user.user_id}>{user.display_name}</option>)}
          </select>
        </label>}
        <Button size="sm" aria-expanded={filtersOpen} onClick={() => setFiltersOpen((open) => !open)}>篩選{activeFilterCount > 0 ? ` ${activeFilterCount}` : ""}</Button>
      </section>

      {filtersOpen && <section className={c.filterDrawer} aria-label="進階篩選">
        <div className={c.filterDrawerHead}><div><h2>進階篩選</h2><p className={styles.meta}>縮小案件範圍，條件會保留在網址中。</p></div><Button size="sm" onClick={resetFilters}>清除篩選</Button></div>
        <div className={c.filterGrid}>
          <label className={styles.field}><span className={styles.label}>案件狀態</span><select className={styles.input} value={rawQuery.status ?? ""} onChange={(event) => setParam("status", event.target.value || null)}><option value="">全部狀態</option>{STATUSES.map((status) => <option key={status} value={status}>{CASE_STATUS_LABELS[status]}</option>)}</select></label>
          <label className={styles.field}><span className={styles.label}>開案日起</span><input className={styles.input} type="date" value={rawQuery.sent_from ?? ""} onChange={(event) => setParam("from", event.target.value || null)} /></label>
          <label className={styles.field}><span className={styles.label}>開案日迄</span><input className={styles.input} type="date" value={rawQuery.sent_to ?? ""} onChange={(event) => setParam("to", event.target.value || null)} /></label>
          <label className={c.checkRow}><input type="checkbox" checked={!!rawQuery.overdue} onChange={(event) => setParam("overdue", event.target.checked ? "1" : null)} />只看有待辦提醒的</label>
        </div>
      </section>}

      <section className={styles.card} aria-labelledby="case-list-title">
        <div className={c.listHeader}><div><h2 id="case-list-title" className={styles.cardTitle}>{queueLabel(effectiveQueue, isManager)}</h2><p className={styles.meta}>共 {total} 件</p></div><span className={c.pageSummary}>{total === 0 ? "顯示 0 件" : `顯示 ${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} / ${total}`}</span></div>
        {isLoading ? <Loading /> : error ? <ErrorState error={error} onRetry={() => void refetch()} /> : !data || data.items.length === 0 ? <Empty title="目前沒有需要處理的案件">可以切換其他工作佇列，或調整搜尋與進階篩選。</Empty> : (
          <div className={c.caseTable} role="table" aria-label="案件列表">
            <div className={c.caseHeader} role="row"><span role="columnheader">案件</span><span role="columnheader">公司</span><span role="columnheader">狀態</span><span role="columnheader">負責人</span><span role="columnheader">下一步</span></div>
            <div role="rowgroup">{data.items.map((item) => <Link key={item.case_id} to={`/cases/${item.case_id}${search}`} className={c.caseRow} role="row">
              <span className={c.caseNo}>{item.case_no}</span><span className={c.companyCell}><strong>{item.company_name}</strong><small>{item.contact_name ?? item.contact_email ?? "未指定聯絡人"}</small></span><span><Tag tone={CASE_STATUS_TONE[item.status]}>{CASE_STATUS_LABELS[item.status]}</Tag></span><span className={c.mutedCell}>{item.owner_name ?? "未指定"}</span><span className={item.reminders.length > 0 ? c.nextStepAlert : c.nextStep}>{nextStep(item)}</span>
            </Link>)}</div>
          </div>
        )}
        {total > 0 && <Pagination page={page} pageCount={pageCount} onPage={(next) => setParam("page", String(next), false)} />}
      </section>
      <Modal open={helpOpen} onOpenChange={setHelpOpen} title="案件說明">
        <p>每封開發信或「加入追蹤」都會開一件案件。案件頁只記錄您手動回填的聯絡結果，系統不會讀取您的信箱。</p>
      </Modal>
    </main>
  );
}

function QueueTab({ active, count, onClick, children }: { active: boolean; count: number; onClick: () => void; children: string }) {
  return <button type="button" className={c.queueTab} aria-pressed={active} onClick={onClick}><span>{children}</span><strong>{count}</strong></button>;
}

function Pagination({ page, pageCount, onPage }: { page: number; pageCount: number; onPage: (page: number) => void }) {
  return <nav className={c.pagination} aria-label="案件分頁"><Button size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>上一頁</Button><span>第 {page} / {pageCount} 頁</span><Button size="sm" disabled={page >= pageCount} onClick={() => onPage(page + 1)}>下一頁</Button></nav>;
}

function queueLabel(queue: CaseQueue, isManager: boolean): string {
  if (queue === "todo") return isManager ? "團隊待辦" : "我的待辦";
  if (queue === "overdue") return "逾期案件";
  if (queue === "follow_up") return "待追蹤案件";
  return "全部案件";
}

function nextStep(item: { status: CaseStatus; next_follow_up: string | null; closed_at: string | null; reminders: string[] }): string {
  if (item.closed_at) return "已結案";
  if (item.reminders.includes("overdue_report")) return "逾期，請回報";
  if (item.reminders.includes("follow_up_due") || item.reminders.includes("no_response")) return "今天追蹤";
  if (item.next_follow_up) return `追蹤 ${formatDate(item.next_follow_up)}`;
  if (item.status === "tracking") return "安排首次聯絡";
  if (item.status === "sent") return "等待回覆";
  return "等待處理";
}
