import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { downloadCases, type CaseQuery } from "../../api/endpoints";
import { useCases, useDimensions } from "../../api/hooks";
import type { CaseStatus } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { Button } from "../../components/Button";
import { Empty, ErrorState, InlineError, Loading } from "../../components/StateView";
import { Tag } from "../../components/Tag";
import { saveBlob } from "../../lib/download";
import { CASE_STATUS_LABELS, CASE_STATUS_TONE, formatDate, REMINDER_LABELS } from "../../lib/labels";
import styles from "../Page.module.css";
import { CasePanel } from "./CasePanel";
import c from "./Cases.module.css";

const STATUSES = Object.keys(CASE_STATUS_LABELS) as CaseStatus[];

/** 網址參數 ⇄ 案件篩選（F-CASE-4：篩選反映在網址上，可以分享） */
export function readCaseQuery(sp: URLSearchParams): CaseQuery {
  const status = sp.get("status");
  const owner = Number(sp.get("owner"));
  return {
    status: status && (STATUSES as string[]).includes(status) ? status : null,
    owner: Number.isInteger(owner) && owner > 0 ? owner : null,
    sent_from: sp.get("from") || null,
    sent_to: sp.get("to") || null,
    overdue: sp.get("overdue") === "1",
  };
}

/** 案件追蹤（SPEC 6.2 /cases、/cases/:id · M3-11a、F-CASE-4） */
export function CasesPage() {
  const selected = Number(useParams().id) || null;
  const [sp, setSp] = useSearchParams();
  const q = readCaseQuery(sp);
  const { data, isLoading, error, refetch } = useCases(q);
  const { isManager } = useAuth();
  const dims = useDimensions();
  const [exportError, setExportError] = useState<unknown>(null);
  const search = sp.toString() ? `?${sp.toString()}` : "";

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(sp);
    if (value) next.set(key, value);
    else next.delete(key);
    setSp(next, { replace: true });
  };

  const doExport = async () => {
    setExportError(null);
    try {
      saveBlob(await downloadCases(q), "cases");
    } catch (err) {
      setExportError(err);
    }
  };

  const total = data ? Object.values(data.counts).reduce((a, b) => a + b, 0) : 0;

  return (
    <>
      <header className={styles.head}>
        <div className={c.headRow}>
          <h1 className={styles.title}>案件追蹤</h1>
          <Button onClick={() => void doExport()}>匯出 CSV</Button>
        </div>
        <p className={styles.meta}>
          每封開發信或「加入追蹤」都會開一件案件。客戶的回覆請在這裡回填，系統不會讀您的信箱。
        </p>
        <InlineError error={exportError} />
      </header>

      {/* 區塊：各狀態件數＋篩選 */}
      <section className={styles.card} aria-label="篩選">
        <div className={c.chips} role="group" aria-label="依狀態篩選">
          <button type="button" className={c.chip} aria-pressed={!q.status} onClick={() => setParam("status", null)}>
            全部 <span className={c.chipCount}>{total}</span>
          </button>
          {STATUSES.map((s) => (
            <button
              key={s}
              type="button"
              className={c.chip}
              aria-pressed={q.status === s}
              onClick={() => setParam("status", q.status === s ? null : s)}
            >
              {CASE_STATUS_LABELS[s]} <span className={c.chipCount}>{data?.counts[s] ?? 0}</span>
            </button>
          ))}
        </div>
        <div className={c.filters}>
          <label className={styles.field}>
            <span className={styles.label}>開案日起</span>
            <input
              type="date"
              className={styles.input}
              value={q.sent_from ?? ""}
              onChange={(e) => setParam("from", e.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>開案日迄</span>
            <input
              type="date"
              className={styles.input}
              value={q.sent_to ?? ""}
              onChange={(e) => setParam("to", e.target.value)}
            />
          </label>
          {isManager && (
            <label className={styles.field}>
              <span className={styles.label}>負責業務</span>
              <select
                className={styles.input}
                value={q.owner ?? ""}
                onChange={(e) => setParam("owner", e.target.value)}
              >
                <option value="">全部</option>
                {dims.data?.users.map((u) => (
                  <option key={u.user_id} value={u.user_id}>
                    {u.display_name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className={c.checkRow}>
            <input
              type="checkbox"
              className={c.check}
              checked={!!q.overdue}
              onChange={(e) => setParam("overdue", e.target.checked ? "1" : null)}
            />
            只看有待辦提醒的
          </label>
        </div>
      </section>

      <div className={c.layout}>
        <section className={styles.card} aria-labelledby="case-list-title">
          <h2 id="case-list-title" className={styles.cardTitle}>
            案件（{data?.items.length ?? 0}）
          </h2>
          {isLoading ? (
            <Loading />
          ) : error ? (
            <ErrorState error={error} onRetry={() => void refetch()} />
          ) : !data || data.items.length === 0 ? (
            <Empty title="沒有符合條件的案件">寄出開發信或在推薦清單按「加入追蹤」後，案件會出現在這裡。</Empty>
          ) : (
            <ul className={c.list}>
              {data.items.map((x) => (
                <li key={x.case_id}>
                  <Link
                    to={`/cases/${x.case_id}${search}`}
                    className={c.item}
                    aria-current={x.case_id === selected ? "page" : undefined}
                  >
                    <span className={c.itemTop}>
                      <span>
                        {x.case_no} {x.company_name}
                      </span>
                      <Tag tone={CASE_STATUS_TONE[x.status]}>{CASE_STATUS_LABELS[x.status]}</Tag>
                    </span>
                    <span className={c.itemMeta}>
                      {x.owner_name} · 開案 {formatDate(x.opened_at)}
                      {x.next_follow_up && ` · 下次追蹤 ${x.next_follow_up}`}
                    </span>
                    {x.reminders.length > 0 && (
                      <span className={c.tags}>
                        {x.reminders.map((r) => (
                          <Tag key={r} tone="warning">
                            {REMINDER_LABELS[r]}
                          </Tag>
                        ))}
                      </span>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
        {selected ? (
          <CasePanel key={selected} caseId={selected} />
        ) : (
          <section className={styles.card}>
            <Empty title="選一件案件">左邊點一件案件，就能看時間軸並回填客戶的回覆。</Empty>
          </section>
        )}
      </div>
    </>
  );
}
