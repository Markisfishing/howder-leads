import { useKpis } from "../../api/hooks";
import styles from "./Recommendations.module.css";

/** 區塊：KPI 卡 · 業務一進來先看到今天要處理多少（F-REC-5）。數字都由後端 view 算好 */
export function KpiCards() {
  const { data, isError } = useKpis();
  const v = (n: number | undefined) => (n === undefined ? "…" : n.toLocaleString("zh-TW"));
  const rate = data?.reply_rate == null ? "—" : `${(Number(data.reply_rate) * 100).toFixed(1)}%`;
  if (isError) return null; // KPI 失敗不擋住清單

  return (
    <section className={styles.kpis} aria-label="重點指標">
      <article className={styles.kpi}>
        <p className={styles.kpiLabel}>待審核</p>
        <p className={styles.kpiValue}>{v(data?.pending_review)}</p>
        <p className={styles.kpiHint}>
          已審 {data ? data.total_companies - data.pending_review : "…"} / {v(data?.total_companies)}
        </p>
      </article>
      <article className={styles.kpi}>
        <p className={styles.kpiLabel}>5 星推薦</p>
        <p className={styles.kpiValue}>{v(data?.five_star)}</p>
        <p className={styles.kpiHint}>使用可能性高</p>
      </article>
      <article className={styles.kpi}>
        <p className={styles.kpiLabel}>近 7 天已寄出</p>
        <p className={styles.kpiValue}>{v(data?.sent_7d)}</p>
        <p className={styles.kpiHint}>依實際寄出時間計算</p>
      </article>
      <article className={styles.kpi}>
        <p className={styles.kpiLabel}>回覆率</p>
        <p className={styles.kpiValue}>{rate}</p>
        <p className={styles.kpiHint}>寄出滿 10 封後顯示</p>
      </article>
    </section>
  );
}
