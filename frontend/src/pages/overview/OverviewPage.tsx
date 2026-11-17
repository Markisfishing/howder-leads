import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useDimensions, useOverview } from "../../api/hooks";
import type { Overview, OverviewQuery } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { Empty, ErrorState, Loading } from "../../components/StateView";
import { Tag } from "../../components/Tag";
import { formatTwd, funnelEntries } from "../../lib/labels";
import styles from "../Page.module.css";
import o from "./Overview.module.css";

const DATE = /^\d{4}-\d{2}-\d{2}$/;

/** 網址參數 ⇄ 總覽篩選（日期區間、產業、產品類型、業務） */
export function readOverviewQuery(sp: URLSearchParams): OverviewQuery {
  const from = sp.get("from") ?? "";
  const to = sp.get("to") ?? "";
  const industry = Number(sp.get("industry"));
  const owner = Number(sp.get("owner"));
  return {
    from: DATE.test(from) ? from : null,
    to: DATE.test(to) ? to : null,
    industry: Number.isInteger(industry) && industry > 0 ? industry : null,
    product_type: sp.get("product") ?? "",
    owner: Number.isInteger(owner) && owner > 0 ? owner : null,
  };
}

/** 比例字串（"0.2667"）→ 26.7%；樣本不足（null）顯示 — */
export function formatRate(rate: string | null): string {
  return rate === null ? "—" : `${(Number(rate) * 100).toFixed(1)}%`;
}

/** 待辦提醒點進去的清單（F-DASH-4） */
export const REMINDER_LINKS: Record<string, string> = {
  overdue_report: "/cases?overdue=1&status=sent",
  follow_up_due: "/cases?overdue=1",
  no_response: "/cases?status=no_response",
  pending_review: "/recommendations?status=pending_review",
};

/** 總覽（SPEC 6.2 /overview · M3-12b、F-DASH-1～4）。數字都由後端 view 算好，這裡只顯示 */
export function OverviewPage() {
  const [sp, setSp] = useSearchParams();
  const q = readOverviewQuery(sp);
  const { data, isLoading, error, refetch } = useOverview(q);
  const { isManager } = useAuth();
  const dims = useDimensions();
  const [product, setProduct] = useState(q.product_type);

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(sp);
    if (value) next.set(key, value);
    else next.delete(key);
    setSp(next, { replace: true });
  };

  // 產品類型打字停 300ms 才查詢
  useEffect(() => {
    if (product === q.product_type) return;
    const t = setTimeout(() => setParam("product", product.trim() || null), 300);
    return () => clearTimeout(t);
  });

  return (
    <>
      <header className={styles.head}>
        <h1 className={styles.title}>總覽</h1>
        <p className={styles.meta}>
          {isManager && !q.owner ? "全團隊" : "我負責的案件"}的寄信、回覆與成交；名單數是全公司共用的名單池。日期區間以寄出日計算。
        </p>
      </header>

      {/* 區塊：篩選 */}
      <section className={styles.card} aria-label="篩選">
        <div className={o.filters}>
          <label className={styles.field}>
            <span className={styles.label}>寄出日起</span>
            <input
              type="date"
              className={styles.input}
              value={q.from ?? ""}
              onChange={(e) => setParam("from", e.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>寄出日迄</span>
            <input
              type="date"
              className={styles.input}
              value={q.to ?? ""}
              onChange={(e) => setParam("to", e.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>產業</span>
            <select
              className={styles.input}
              value={q.industry ?? ""}
              onChange={(e) => setParam("industry", e.target.value)}
            >
              <option value="">全部產業</option>
              {dims.data?.industries.map((i) => (
                <option key={i.industry_id} value={i.industry_id}>
                  {i.name}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.field}>
            <span className={styles.label}>產品類型</span>
            <input
              type="search"
              className={styles.input}
              placeholder="例如 控制盤"
              value={product}
              onChange={(e) => setProduct(e.target.value)}
            />
          </label>
          {isManager && (
            <label className={styles.field}>
              <span className={styles.label}>業務</span>
              <select className={styles.input} value={q.owner ?? ""} onChange={(e) => setParam("owner", e.target.value)}>
                <option value="">全團隊</option>
                {dims.data?.users.map((u) => (
                  <option key={u.user_id} value={u.user_id}>
                    {u.display_name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      </section>

      {isLoading ? (
        <Loading />
      ) : error || !data ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : (
        <OverviewBody data={data} />
      )}
    </>
  );
}

function OverviewBody({ data }: { data: Overview }) {
  const k = data.kpis;
  const top = data.funnel[0]?.count ?? 0;
  const kpis: [string, string, string][] = [
    ["名單公司數", k.companies.toLocaleString("zh-TW"), "共用名單池"],
    ["高優先名單", k.high_priority.toLocaleString("zh-TW"), "優先級 A（5 星）"],
    ["已寄開發信", k.sent.toLocaleString("zh-TW"), "依案件計算"],
    ["回覆率", formatRate(k.reply_rate), k.reply_rate === null ? "樣本不足（寄出未滿 10 件）" : `回覆 ${k.replied} 件`],
    ["成交數", k.won.toLocaleString("zh-TW"), `金額 ${formatTwd(k.won_amount_twd)}`],
  ];

  return (
    <>
      {/* 區塊：KPI（F-DASH-1） */}
      <section className={o.kpis} aria-label="重點指標">
        {kpis.map(([label, value, hint]) => (
          <article key={label} className={o.kpi}>
            <p className={styles.countLabel}>{label}</p>
            <p className={o.kpiValue}>{value}</p>
            <p className={styles.hint}>{hint}</p>
          </article>
        ))}
      </section>

      <div className={o.grid}>
        {/* 區塊：名單漏斗（F-DASH-2） */}
        <section className={styles.card} aria-labelledby="funnel-title">
          <h2 id="funnel-title" className={styles.cardTitle}>
            名單漏斗
          </h2>
          {data.mle_funnel && Object.keys(data.mle_funnel).length > 0 && (
            <p className={styles.hint}>
              MLE 前段：
              {funnelEntries(data.mle_funnel)
                .map(([label, n]) => `${label} ${n.toLocaleString("zh-TW")}`)
                .join(" → ")}
            </p>
          )}
          <ol className={o.funnel}>
            {data.funnel.map((s) => (
              <li key={s.key} className={o.stage}>
                <span className={o.stageHead}>
                  <strong>{s.label}</strong>
                  <span>
                    {s.count.toLocaleString("zh-TW")}
                    {s.rate !== null && <span className={styles.hint}>（留存 {formatRate(s.rate)}）</span>}
                  </span>
                </span>
                <span className={o.bar} aria-hidden="true">
                  <span className={o.barFill} style={{ width: `${top ? (s.count / top) * 100 : 0}%` }} />
                </span>
              </li>
            ))}
          </ol>
        </section>

        {/* 區塊：待辦提醒（F-DASH-4） */}
        <section className={styles.card} aria-labelledby="reminder-title">
          <h2 id="reminder-title" className={styles.cardTitle}>
            待辦提醒
          </h2>
          <ul className={o.reminders}>
            {data.reminders.map((r) => (
              <li key={r.kind}>
                <Link to={REMINDER_LINKS[r.kind] ?? "/cases"} className={o.reminder}>
                  <span>{r.label}</span>
                  <Tag tone={r.count > 0 ? "warning" : "neutral"}>{r.count} 件</Tag>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {/* 區塊：各來源回覆率（F-DASH-3） */}
      <section className={styles.card} aria-labelledby="source-title">
        <h2 id="source-title" className={styles.cardTitle}>
          各來源回覆率
        </h2>
        {data.by_source.length === 0 ? (
          <Empty title="還沒有寄出的開發信">寄出後，這裡會依名單來源比較回覆率。</Empty>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>資料來源</th>
                  <th>寄出</th>
                  <th>回覆</th>
                  <th>回覆率</th>
                </tr>
              </thead>
              <tbody>
                {data.by_source.map((s) => (
                  <tr key={s.source}>
                    <td>{s.source}</td>
                    <td>{s.sent}</td>
                    <td>{s.replied}</td>
                    <td>{s.insufficient ? <Tag tone="neutral">樣本不足</Tag> : formatRate(s.reply_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
