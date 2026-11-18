import { useState, type FormEvent } from "react";

import { downloadReviewExport } from "../api/endpoints";
import { useImportActions, useImports } from "../api/hooks";
import type { ImportBatchDetail } from "../api/types";
import { Button } from "../components/Button";
import { Empty, ErrorState, InlineError, Loading } from "../components/StateView";
import { Tag } from "../components/Tag";
import { formatDateTime, funnelEntries } from "../lib/labels";
import styles from "./Page.module.css";

const ACTION_LABELS = { create: "新增", update: "更新", unchanged: "沒變", skip: "略過（網址無效）" } as const;
const BATCH_STATUS = {
  previewed: { label: "預覽中", tone: "warning" },
  committed: { label: "已匯入", tone: "success" },
  cancelled: { label: "已取消", tone: "neutral" },
} as const;

/** 名單管理（SPEC 6.2 /admin/imports · F-IMP-1~6、M3-06b）：上傳 → 預覽差異 → 確認匯入；也可下載審核結果給 MLE */
export function AdminImportsPage() {
  const { upload, commit, cancel, open } = useImportActions();
  const history = useImports();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportBatchDetail | null>(null);
  const [notice, setNotice] = useState("");
  const [exportError, setExportError] = useState<unknown>(null);
  const [section, setSection] = useState<"import" | "history" | "export">("import");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setNotice("");
    upload.mutate({ file }, { onSuccess: (batch) => { setPreview(batch); setSection("import"); } });
  };

  const doCommit = () => {
    if (!preview) return;
    commit.mutate(preview.batch_id, {
      onSuccess: (b) => {
        setNotice(`已匯入：新增 ${b.rows_created}、更新 ${b.rows_updated}（模型版本 run #${b.run_id}）`);
        setPreview(null);
        setFile(null);
      },
    });
  };

  const doCancel = () => {
    if (!preview) return;
    cancel.mutate(preview.batch_id, {
      onSuccess: () => {
        setNotice("已取消這次匯入");
        setPreview(null);
      },
    });
  };

  const doExport = async () => {
    setExportError(null);
    try {
      const blob = await downloadReviewExport();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `reviews_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err);
    }
  };

  return (
    <>
      <header className={styles.head}>
        <h1 className={styles.title}>名單管理</h1>
        <p className={styles.meta}>上傳 CSV 或 Excel，確認資料差異後再正式匯入。</p>
      </header>

      <div aria-live="polite">{notice && <p className={styles.hint}>{notice}</p>}</div>

      <nav className={styles.sectionTabs} aria-label="名單管理功能">
        <button type="button" aria-pressed={section === "import"} className={styles.sectionTab} onClick={() => setSection("import")}>匯入名單</button>
        <button type="button" aria-pressed={section === "history"} className={styles.sectionTab} onClick={() => setSection("history")}>匯入紀錄</button>
        <button type="button" aria-pressed={section === "export"} className={styles.sectionTab} onClick={() => setSection("export")}>匯出審核結果</button>
      </nav>

      {/* 區塊：上傳 */}
      {section === "import" && <section className={styles.card}>
        <h2 className={styles.cardTitle}>上傳檔案</h2>
        <form className={styles.form} onSubmit={submit}>
          <label className={styles.field}>
            <span className={styles.label}>檔案（.csv / .xlsx，10 MB 以內）</span>
            <input
              className={styles.input}
              type="file"
              accept=".csv,.xlsx"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <Button variant="primary" type="submit" disabled={!file} busy={upload.isPending}>
            上傳並預覽
          </Button>
        </form>
        <InlineError error={upload.error} />
      </section>}

      {/* 區塊：預覽 */}
      {section === "import" && preview && <PreviewCard batch={preview} onCommit={doCommit} onCancel={doCancel} />}
      <InlineError error={commit.error ?? cancel.error ?? open.error} />

      {/* 區塊：審核結果匯出（給 MLE 調模型） */}
      {section === "export" && <section className={styles.card}>
        <h2 className={styles.cardTitle}>審核結果匯出</h2>
        <p className={styles.hint}>下載所有審核紀錄（含排除原因與產業修正），交給 MLE 調整模型。</p>
        <div className={styles.actions}>
          <Button onClick={() => void doExport()}>下載 CSV</Button>
        </div>
        <InlineError error={exportError} />
      </section>}

      {/* 區塊：匯入紀錄 */}
      {section === "history" && <section className={styles.card}>
        <h2 className={styles.cardTitle}>匯入紀錄</h2>
        {history.isLoading ? (
          <Loading />
        ) : history.error ? (
          <ErrorState error={history.error} onRetry={() => void history.refetch()} />
        ) : !history.data?.length ? (
          <Empty title="還沒有匯入紀錄" />
        ) : (
          <div className={styles.tableWrap}>
            <table className={`${styles.table} ${styles.mobileTable}`}>
              <thead>
                <tr>
                  <th>時間</th>
                  <th>檔案</th>
                  <th>狀態</th>
                  <th>新增</th>
                  <th>更新</th>
                  <th>錯誤</th>
                  <th>模型版本</th>
                  <th>
                    <span className="visually-hidden">動作</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {history.data.map((b) => (
                  <tr key={b.batch_id}>
                    <td data-label="時間" className={styles.nowrap}>{formatDateTime(b.created_at)}</td>
                    <td data-label="檔案">{b.file_name ?? b.source}</td>
                    <td data-label="狀態">
                      <Tag tone={BATCH_STATUS[b.status].tone}>{BATCH_STATUS[b.status].label}</Tag>
                    </td>
                    <td data-label="新增">{b.rows_created}</td>
                    <td data-label="更新">{b.rows_updated}</td>
                    <td data-label="錯誤">{b.rows_error}</td>
                    <td data-label="模型版本">{b.run_id ? `#${b.run_id}${b.model_name ? ` ${b.model_name}` : ""}` : "—"}</td>
                    <td data-label="動作">
                      {b.status === "previewed" && (
                        <Button
                          size="sm"
                          busy={open.isPending && open.variables === b.batch_id}
                          onClick={() => open.mutate(b.batch_id, { onSuccess: setPreview })}
                        >
                          繼續
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>}
    </>
  );
}

function PreviewCard({
  batch: b,
  onCommit,
  onCancel,
}: {
  batch: ImportBatchDetail;
  onCommit: () => void;
  onCancel: () => void;
}) {
  const hasErrors = b.errors.length > 0;
  // 有錯誤的列不會寫入（後端 commit 只寫通過檢查的列）；全部都有錯才不能匯入
  const writable = b.rows_created + b.rows_updated;
  return (
    <section className={styles.card} aria-label="匯入預覽">
      <h2 className={styles.cardTitle}>預覽：{b.file_name}</h2>
      <div className={styles.counts}>
        {[
          ["總列數", b.rows_total],
          ["新增", b.rows_created],
          ["更新", b.rows_updated],
          ["沒變", b.rows_unchanged],
          ["略過", b.rows_skipped],
          ["錯誤", b.rows_error],
        ].map(([label, value]) => (
          <div key={label} className={styles.count}>
            <p className={styles.countLabel}>{label}</p>
            <p className={styles.countValue}>{value}</p>
          </div>
        ))}
      </div>

      {/* 區塊：MLE 附上的漏斗前段數字（只顯示，不重算） */}
      {b.funnel && Object.keys(b.funnel).length > 0 && (
        <>
          <h3 className={styles.label}>漏斗前段（MLE 提供）</h3>
          <div className={styles.counts}>
            {funnelEntries(b.funnel).map(([label, value]) => (
              <div key={label} className={styles.count}>
                <p className={styles.countLabel}>{label}</p>
                <p className={styles.countValue}>{value.toLocaleString("zh-TW")}</p>
              </div>
            ))}
          </div>
        </>
      )}

      {/* 區塊：不擋匯入的提示（看不懂的欄位、沒有資料來源欄） */}
      {b.warnings.length > 0 && (
        <ul className={styles.hint} aria-label="匯入提示">
          {b.warnings.map((w) => (
            <li key={w.field}>提示：{w.message}</li>
          ))}
        </ul>
      )}
      {b.rows_skipped > 0 && (
        <p className={styles.hint}>有 {b.rows_skipped} 列網址狀態是 invalid，不會進名單（SPEC 8.4）。</p>
      )}

      {hasErrors && (
        <>
          <p className={styles.hint} role="alert">
            有 {b.errors.length} 列有錯誤，確認匯入時會略過這些列；要匯入它們，請修正檔案後重新上傳。
          </p>
          <div className={styles.tableWrap}>
            <table className={`${styles.table} ${styles.mobileTable}`}>
              <thead>
                <tr>
                  <th>列</th>
                  <th>欄位</th>
                  <th>問題</th>
                </tr>
              </thead>
              <tbody>
                {b.errors.map((e, i) => (
                  <tr key={i}>
                    <td data-label="列">{e.row}</td>
                    <td data-label="欄位">{e.field}</td>
                    <td data-label="問題">{e.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {b.rows.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={`${styles.table} ${styles.mobileTable}`}>
            <thead>
              <tr>
                <th>列</th>
                <th>動作</th>
                <th>統編</th>
                <th>公司</th>
                <th>等級</th>
                <th>星等</th>
                <th>來源</th>
                <th>變更欄位</th>
              </tr>
            </thead>
            <tbody>
              {b.rows.map((r) => (
                <tr key={r.row}>
                  <td data-label="列">{r.row}</td>
                  <td data-label="動作" className={styles.nowrap}>{ACTION_LABELS[r.action]}</td>
                  <td data-label="統編" className="mono">{r.tax_id}</td>
                  <td data-label="公司">{r.name}</td>
                  <td data-label="等級">{r.priority}</td>
                  <td data-label="星等">{r.fit_stars?.toFixed(1) ?? "—"}</td>
                  <td data-label="來源">{r.source ?? "未標示"}</td>
                  <td data-label="變更欄位">{r.changed_fields?.join("、") ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className={styles.actions}>
        <Button onClick={onCancel}>取消這次匯入</Button>
        <Button variant="primary" disabled={writable === 0} onClick={onCommit}>
          {hasErrors ? `略過錯誤列，匯入 ${writable} 筆` : "確認匯入"}
        </Button>
      </div>
    </section>
  );
}
