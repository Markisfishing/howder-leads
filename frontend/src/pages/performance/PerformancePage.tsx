import { useSearchParams } from "react-router-dom";

import { usePerformance } from "../../api/hooks";
import type { PerfBreakdown, PerfRow } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { Empty, ErrorState, Loading } from "../../components/StateView";
import { Tag } from "../../components/Tag";
import { formatTwd } from "../../lib/labels";
import styles from "../Page.module.css";

type RangeKey = "30d" | "90d" | "this_month" | "all";
const RANGE_LABELS: Record<RangeKey, string> = {
  "30d": "最近 30 天",
  "90d": "最近 90 天",
  this_month: "本月",
  all: "全部時間",
};
const TABS: { key: PerfBreakdown; label: string; first: string }[] = [
  { key: "stars", label: "星級", first: "推薦度" },
  { key: "source", label: "資料來源", first: "來源" },
  { key: "tag", label: "產品標籤", first: "標籤" },
  { key: "template", label: "郵件模板", first: "模板" },
  { key: "rep", label: "業務", first: "業務" },
];

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** 日期區間選項 → API 的 from／to（寄出日）；全部時間不帶日期 */
export function rangeFor(key: RangeKey, now = new Date()): { from: string | null; to: string | null } {
  if (key === "all") return { from: null, to: null };
  const from = new Date(now);
  if (key === "30d") from.setDate(from.getDate() - 29);
  if (key === "90d") from.setDate(from.getDate() - 89);
  if (key === "this_month") from.setDate(1);
  return { from: ymd(from), to: ymd(now) };
}

/** 比例字串（"0.2667"）→ 26.7%；樣本不足（null）顯示 —（比例由後端算，這裡只轉格式） */
export function formatRate(rate: string | null): string {
  return rate === null ? "—" : `${(Number(rate) * 100).toFixed(1)}%`;
}

/** 績效頁（SPEC 6.2 /performance · M4-01c、F-TRK-5）：表格為主，比例旁一定附件數，樣本不足要標示 */
export function PerformancePage() {
  const { isManager } = useAuth();
  const [sp, setSp] = useSearchParams();
  const tab = TABS.find((t) => t.key === sp.get("by"))?.key ?? "stars";
  const range = (Object.keys(RANGE_LABELS) as RangeKey[]).find((k) => k === sp.get("range")) ?? "90d";
  const { data, isLoading, error, refetch } = usePerformance(tab, rangeFor(range));
  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(sp);
    next.set(key, value);
    setSp(next, { replace: true });
  };
  const first = TABS.find((t) => t.key === tab)?.first ?? "";

  return (
    <>
      <header className={styles.head}>
        <h1 className={styles.title}>績效</h1>
        <p className={styles.meta}>
          {isManager ? "全團隊" : "我的"}案件 · 日期依寄出日計算 · 寄出少於 10 件不算比例（標「樣本不足」）
        </p>
      </header>

      <nav className={styles.sectionTabs} aria-label="績效分類">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={styles.sectionTab}
            aria-pressed={tab === t.key}
            onClick={() => setParam("by", t.key)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <label className={styles.field}>
        <span className={styles.label}>寄出日區間</span>
        <select className={styles.input} value={range} onChange={(e) => setParam("range", e.target.value)}>
          {(Object.keys(RANGE_LABELS) as RangeKey[]).map((k) => (
            <option key={k} value={k}>
              {RANGE_LABELS[k]}
            </option>
          ))}
        </select>
      </label>

      <section className={styles.card} aria-labelledby="perf-title">
        <h2 id="perf-title" className={styles.cardTitle}>
          各{TABS.find((t) => t.key === tab)?.label}成效
        </h2>
        {isLoading ? (
          <Loading />
        ) : error || !data ? (
          <ErrorState error={error} onRetry={() => void refetch()} />
        ) : data.items.length === 0 ? (
          <Empty title="這個區間還沒有寄出的案件">換個日期區間，或等業務寄出邀請信後再回來看。</Empty>
        ) : (
          <PerfTableView first={first} rows={data.items} />
        )}
      </section>
    </>
  );
}

function PerfTableView({ first, rows }: { first: string; rows: PerfRow[] }) {
  return (
    <div className={styles.tableWrap}>
      <table className={`${styles.table} ${styles.mobileTable}`}>
        <thead>
          <tr>
            <th>{first}</th>
            <th>寄出</th>
            <th>回覆</th>
            <th>回覆率</th>
            <th>成交</th>
            <th>成交率</th>
            <th>成交金額</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <td data-label={first}>
                {r.label} {r.insufficient && <Tag tone="warning">樣本不足</Tag>}
              </td>
              <td data-label="寄出">{r.sent} 件</td>
              <td data-label="回覆">{r.replied} 件</td>
              <td data-label="回覆率">{formatRate(r.reply_rate)}</td>
              <td data-label="成交">{r.won} 件</td>
              <td data-label="成交率">{formatRate(r.win_rate)}</td>
              <td data-label="成交金額">{formatTwd(r.won_amount_twd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
