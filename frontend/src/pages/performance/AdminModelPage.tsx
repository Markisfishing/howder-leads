import { useState } from "react";

import { useRejectReport } from "../../api/hooks";
import type { RejectReason } from "../../api/types";
import { Empty, ErrorState, Loading } from "../../components/StateView";
import { formatDateTime, REJECT_REASON_LABELS } from "../../lib/labels";
import styles from "../Page.module.css";
import { formatRate } from "./PerformancePage";

/** 名單品質（SPEC 6.2 /admin/model · M4-02b、F-MLE-1）：各匯入批次的排除原因分布。內部用，不回傳給 MLE */
export function AdminModelPage() {
  const [runId, setRunId] = useState<number | null>(null);
  const { data, isLoading, error, refetch } = useRejectReport(runId);

  return (
    <>
      <header className={styles.head}>
        <h1 className={styles.title}>名單品質</h1>
        <p className={styles.meta}>看每一批匯入的名單，業務最常因為什麼原因排除，用來判斷名單準不準。</p>
      </header>

      {isLoading ? (
        <Loading />
      ) : error || !data ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : data.runs.length === 0 ? (
        <Empty title="還沒有匯入過名單">到「名單管理」匯入後，這裡就會出現各批次的排除原因。</Empty>
      ) : (
        <>
          <label className={styles.field}>
            <span className={styles.label}>匯入批次</span>
            <select
              className={styles.input}
              value={data.run_id ?? ""}
              onChange={(e) => setRunId(Number(e.target.value))}
            >
              {data.runs.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  #{r.run_id} {r.model_name} · {formatDateTime(r.created_at)}
                </option>
              ))}
            </select>
          </label>
          <section className={styles.card} aria-labelledby="reject-title">
            <h2 id="reject-title" className={styles.cardTitle}>
              排除原因分布（共 {data.total} 家被排除）
            </h2>
            {data.items.length === 0 ? (
              <Empty title="這一批還沒有被排除的公司" />
            ) : (
              <div className={styles.tableWrap}>
                <table className={`${styles.table} ${styles.mobileTable}`}>
                  <thead>
                    <tr>
                      <th>排除原因</th>
                      <th>家數</th>
                      <th>占比</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((i) => (
                      <tr key={i.reason ?? "none"}>
                        <td data-label="排除原因">
                          {i.reason ? (REJECT_REASON_LABELS[i.reason as RejectReason] ?? i.reason) : "（未填原因）"}
                        </td>
                        <td data-label="家數">{i.count} 家</td>
                        <td data-label="占比">{formatRate(i.share)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </>
  );
}
