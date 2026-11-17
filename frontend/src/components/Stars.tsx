import { PRIORITY_LABELS } from "../lib/labels";
import styles from "./Stars.module.css";

/** 星級旁邊一定附等級文字（CLAUDE.md 第 7 節第 7 點）；模型沒評分的公司顯示「未評分」 */
export function Stars({ stars, priority }: { stars: number; priority: string | null }) {
  if (!priority || stars === 0) {
    return <span className={styles.none}>未評分</span>;
  }
  const label = `${stars} 星，${priority} ${PRIORITY_LABELS[priority] ?? ""}`;
  return (
    <span className={styles.stars} role="img" aria-label={label} title={label}>
      <span className={styles.on} aria-hidden="true">
        {"★".repeat(stars)}
      </span>
      <span className={styles.off} aria-hidden="true">
        {"★".repeat(5 - stars)}
      </span>
      <span className={styles.grade} aria-hidden="true">
        {priority}
      </span>
    </span>
  );
}
