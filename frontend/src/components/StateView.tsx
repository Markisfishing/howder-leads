import type { ReactNode } from "react";

import styles from "./StateView.module.css";

/** 每個頁面都要處理的「載入中／空資料／錯誤」（CLAUDE.md 第 7 節第 6 點） */
export function Loading({ label = "載入中…" }: { label?: string }) {
  return (
    <div className={styles.box} role="status" aria-live="polite">
      {label}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className={styles.box}>
      <p className={styles.title}>{title}</p>
      {children && <div className={styles.body}>{children}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : "發生未預期的錯誤";
  return (
    <div className={`${styles.box} ${styles.error}`} role="alert">
      <p className={styles.title}>無法載入資料</p>
      <p className={styles.body}>{message}</p>
      {onRetry && (
        <button type="button" className={styles.retry} onClick={onRetry}>
          重試
        </button>
      )}
    </div>
  );
}

/** 表單或操作失敗時的行內訊息 */
export function InlineError({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p className={styles.inline} role="alert">
      {error instanceof Error ? error.message : String(error)}
    </p>
  );
}
