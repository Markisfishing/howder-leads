import { PRIORITY_LABELS } from "../lib/labels";
import styles from "./Stars.module.css";

interface Props {
  stars: number;
  priority: string | null;
  /** 適合度星等（MLE 提供，可到小數一位，例如 "4.5"）；有給就顯示數字，星星依四捨五入（F-REC-1） */
  fitStars?: string | number | null;
}

/** 星級旁邊一定附等級文字（CLAUDE.md 第 7 節第 7 點）；模型沒評分的公司顯示「未評分」 */
export function Stars({ stars, priority, fitStars }: Props) {
  const fit = fitStars === null || fitStars === undefined ? null : Number(fitStars);
  if (!priority || (stars === 0 && !fit)) {
    return <span className={styles.none}>未評分</span>;
  }
  const value = fit ?? stars;
  const filled = Math.min(5, Math.max(0, Math.round(value)));
  const number = fit === null ? String(stars) : fit.toFixed(1);
  const label = `${number} 星，${priority} ${PRIORITY_LABELS[priority] ?? ""}`;
  return (
    <span className={styles.stars} role="img" aria-label={label} title={label}>
      <span className={styles.on} aria-hidden="true">
        {"★".repeat(filled)}
      </span>
      <span className={styles.off} aria-hidden="true">
        {"★".repeat(5 - filled)}
      </span>
      {fit !== null && (
        <span className={styles.number} aria-hidden="true">
          {number}
        </span>
      )}
      <span className={styles.grade} aria-hidden="true">
        {priority}
      </span>
    </span>
  );
}
