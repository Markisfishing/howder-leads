import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useDimensions, useOverview } from "../../api/hooks";
import type { Overview, OverviewQuery } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { Button } from "../../components/Button";
import { ErrorState, Loading } from "../../components/StateView";
import { Tag } from "../../components/Tag";
import { formatTwd } from "../../lib/labels";
import styles from "../Page.module.css";
import o from "./Overview.module.css";

const DATE = /^\d{4}-\d{2}-\d{2}$/;
type DateRangeKey = "7d" | "30d" | "this_month" | "last_month" | "custom";
const DATE_RANGE_LABELS: Record<DateRangeKey, string> = {
  "7d": "最近 7 天",
  "30d": "最近 30 天",
  this_month: "本月",
  last_month: "上月",
  custom: "自訂範圍",
};

/** 網址參數 ⇄ 首頁篩選（日期區間、產業、產品類型、業務） */
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

/** 待辦提醒點進去的清單 */
export const REMINDER_LINKS: Record<string, string> = {
  overdue_report: "/cases?overdue=1&status=sent",
  follow_up_due: "/cases?overdue=1",
  no_response: "/cases?status=no_response",
  pending_review: "/recommendations?status=pending_review",
};

const DEFAULT_DATE_RANGE: Exclude<DateRangeKey, "custom"> = "30d";

function toDateValue(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getDateRange(key: Exclude<DateRangeKey, "custom">, now = new Date()): { from: string; to: string } {
  const to = new Date(now);
  const from = new Date(now);
  if (key === "7d") from.setDate(from.getDate() - 6);
  if (key === "30d") from.setDate(from.getDate() - 29);
  if (key === "this_month") from.setDate(1);
  if (key === "last_month") {
    from.setMonth(from.getMonth() - 1, 1);
    to.setDate(0);
  }
  return { from: toDateValue(from), to: toDateValue(to) };
}

function getDateRangeKey(q: OverviewQuery): DateRangeKey {
  if (!q.from || !q.to) return DEFAULT_DATE_RANGE;
  const matches = (key: Exclude<DateRangeKey, "custom">) => {
    const range = getDateRange(key);
    return q.from === range.from && q.to === range.to;
  };
  return (["7d", "30d", "this_month", "last_month"] as const).find(matches) ?? "custom";
}

/** 首頁（/overview）：成果優先，資料篩選退到第二層。 */
export function OverviewPage() {
  const [sp, setSp] = useSearchParams();
  const rawQuery = readOverviewQuery(sp);
  const selectedDateRange: DateRangeKey = sp.get("range") === "custom" ? "custom" : getDateRangeKey(rawQuery);
  const q = sp.has("from") || sp.has("to") ? rawQuery : { ...rawQuery, ...getDateRange(DEFAULT_DATE_RANGE) };
  const { data, isLoading, error, refetch } = useOverview(q);
  const { isManager } = useAuth();
  const dims = useDimensions();
  const [filterOpen, setFilterOpen] = useState(false);
  const [draftIndustry, setDraftIndustry] = useState("");
  const [draftProduct, setDraftProduct] = useState("");

  useEffect(() => {
    if (sp.has("from") || sp.has("to")) return;
    const range = getDateRange(DEFAULT_DATE_RANGE);
    const next = new URLSearchParams(sp);
    next.set("from", range.from);
    next.set("to", range.to);
    next.delete("range");
    setSp(next, { replace: true });
  }, [setSp, sp]);

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(sp);
    if (value) next.set(key, value);
    else next.delete(key);
    setSp(next, { replace: true });
  };

  const applyFilters = () => {
    const next = new URLSearchParams(sp);
    if (draftIndustry) next.set("industry", draftIndustry);
    else next.delete("industry");
    if (draftProduct.trim()) next.set("product", draftProduct.trim());
    else next.delete("product");
    setSp(next, { replace: true });
    setFilterOpen(false);
  };

  const selectDateRange = (value: DateRangeKey) => {
    if (value === "custom") return;
    const range = getDateRange(value);
    const next = new URLSearchParams(sp);
    next.set("from", range.from);
    next.set("to", range.to);
    next.delete("range");
    setSp(next, { replace: true });
  };

  const toggleFilter = () => {
    if (!filterOpen) {
      setDraftIndustry(q.industry ? String(q.industry) : "");
      setDraftProduct(q.product_type);
    }
    setFilterOpen((open) => !open);
  };

  const activeFilters = [
    q.industry ? dims.data?.industries.find((item) => item.industry_id === q.industry)?.name ?? `產業 ${q.industry}` : null,
    q.product_type ? q.product_type : null,
  ].filter((value): value is string => Boolean(value));

  return (
    <>
      <header className={styles.head}>
        <div className={o.titleRow}>
          <div>
            <h1 className={styles.title}>首頁</h1>
            <p className={styles.meta}>{isManager && !q.owner ? "全團隊" : "我的"} · {DATE_RANGE_LABELS[selectedDateRange]}</p>
          </div>
          <div className={o.filterControls}>
            <label className={o.rangeField}>
              <span className="visually-hidden">日期區間</span>
              <select className={o.rangeSelect} value={selectedDateRange} onChange={(event) => {
                const value = event.target.value as DateRangeKey;
                if (value === "custom") {
                  const next = new URLSearchParams(sp);
                  next.set("range", "custom");
                  setSp(next, { replace: true });
                } else {
                  selectDateRange(value);
                }
              }} aria-label="日期區間">
                {Object.entries(DATE_RANGE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            {isManager && (
              <label className={o.rangeField}>
                <span className="visually-hidden">資料範圍</span>
                <select className={o.rangeSelect} value={q.owner ?? ""} onChange={(event) => setParam("owner", event.target.value || null)} aria-label="資料範圍">
                  <option value="">全團隊</option>
                  {dims.data?.users.map((user) => <option key={user.user_id} value={user.user_id}>{user.display_name}</option>)}
                </select>
              </label>
            )}
            <Button variant="ghost" size="sm" aria-expanded={filterOpen} aria-controls="overview-filter-drawer" onClick={toggleFilter}>
              篩選{activeFilters.length ? `（${activeFilters.length}）` : ""}
            </Button>
          </div>
        </div>
        {activeFilters.length > 0 && <div className={o.activeFilters} aria-label="已套用篩選">{activeFilters.map((filter) => <Tag key={filter} tone="info">{filter} ×</Tag>)}</div>}
      </header>

      {filterOpen && (
        <section id="overview-filter-drawer" className={`${styles.card} ${o.filterDrawer}`} aria-labelledby="filter-title">
          <div className={o.drawerHeader}>
            <h2 id="filter-title" className={styles.cardTitle}>進階篩選</h2>
            <p className={styles.hint}>日期依寄出日計算。</p>
          </div>
          <div className={o.filterGrid}>
            <label className={styles.field}>
              <span className={styles.label}>產業</span>
              <select className={styles.input} value={draftIndustry} onChange={(event) => setDraftIndustry(event.target.value)}>
                <option value="">全部產業</option>
                {dims.data?.industries.map((industry) => <option key={industry.industry_id} value={industry.industry_id}>{industry.name}</option>)}
              </select>
            </label>
            <label className={styles.field}>
              <span className={styles.label}>產品類型</span>
              <input type="search" className={styles.input} placeholder="例如 控制盤" value={draftProduct} onChange={(event) => setDraftProduct(event.target.value)} />
            </label>
            {selectedDateRange === "custom" && (
              <>
                <label className={styles.field}>
                  <span className={styles.label}>寄出日起</span>
                  <input type="date" className={styles.input} value={q.from ?? ""} onChange={(event) => setParam("from", event.target.value || null)} />
                </label>
                <label className={styles.field}>
                  <span className={styles.label}>寄出日迄</span>
                  <input type="date" className={styles.input} value={q.to ?? ""} onChange={(event) => setParam("to", event.target.value || null)} />
                </label>
              </>
            )}
          </div>
          <div className={styles.actions}>
            <Button variant="primary" onClick={applyFilters}>套用篩選</Button>
            <Button variant="ghost" onClick={() => { setDraftIndustry(""); setDraftProduct(""); }}>清除產業與產品</Button>
          </div>
        </section>
      )}

      {isLoading ? <Loading /> : error || !data ? <ErrorState error={error} onRetry={() => void refetch()} /> : <OverviewBody data={data} />}
    </>
  );
}

function OverviewBody({ data }: { data: Overview }) {
  const k = data.kpis;
  const [sourceExpanded, setSourceExpanded] = useState(false);
  const pendingReview = data.reminders.find((reminder) => reminder.kind === "pending_review")?.count ?? 0;
  const comparison = data.comparison;
  const rateDelta = comparison?.reply_rate_delta !== null && comparison?.reply_rate_delta !== undefined ? Number(comparison.reply_rate_delta) * 100 : null;
  const targetRate = comparison ? Number(comparison.reply_rate_target) * 100 : null;
  const primaryKpis = [
    { label: "已寄出", value: k.sent.toLocaleString("zh-TW"), hint: "查看邀請信", insight: comparison ? `較前期 ${formatSigned(comparison.sent_delta)}` : undefined, to: "/campaigns" },
    { label: "回覆率", value: formatRate(k.reply_rate), hint: `回覆 ${k.replied.toLocaleString("zh-TW")} 件`, insight: rateDelta !== null ? `較前期 ${formatSigned(rateDelta, "個百分點")}${targetRate !== null && Number(k.reply_rate ?? 0) < targetRate / 100 ? ` · 低於目標 ${targetRate}%` : ""}` : undefined, to: "/cases?status=replied" },
    { label: "成交", value: k.won.toLocaleString("zh-TW"), hint: "查看成交案件", insight: comparison ? `較前期 ${formatSigned(comparison.won_delta)}` : undefined, to: "/cases?status=won" },
    { label: "成交金額", value: formatTwd(k.won_amount_twd), hint: "查看成交案件", insight: comparison ? `較前期 ${formatTwd(comparison.won_amount_delta_twd)}` : undefined, to: "/cases?status=won", featured: true },
  ];
  const inventoryKpis = [
    { label: "公司總數", value: k.companies, hint: "查看完整推薦清單", to: "/recommendations" },
    { label: "高優先名單", value: k.high_priority, hint: `查看 ${k.high_priority.toLocaleString("zh-TW")} 家`, to: "/recommendations?min_stars=5" },
    { label: "待審核", value: pendingReview, hint: `查看 ${pendingReview.toLocaleString("zh-TW")} 家`, to: REMINDER_LINKS.pending_review ?? "/recommendations?status=pending_review" },
  ];
  const top = data.funnel[0]?.count ?? 0;
  const activeReminders = data.reminders.filter((reminder) => reminder.count > 0);
  const completedReminderCount = data.reminders.length - activeReminders.length;
  const visibleSources = sourceExpanded ? data.by_source : data.by_source.slice(0, 5);

  return (
    <>
      <section aria-labelledby="outcome-title">
        <h2 id="outcome-title" className={o.sectionTitle}>開發成果</h2>
        <div className={o.kpis}>{primaryKpis.map((kpi) => <KpiLink key={kpi.label} {...kpi} />)}</div>
      </section>

      <div className={o.grid}>
        <section className={styles.card} aria-labelledby="funnel-title">
          <h2 id="funnel-title" className={styles.cardTitle}>開發漏斗</h2>
          <ol className={o.funnel}>
            {data.funnel.map((stage) => (
              <li key={stage.key} className={o.stage}>
                <span className={o.stageHead}><strong>{stage.label}</strong><span>{stage.count.toLocaleString("zh-TW")}{stage.rate !== null && <span className={styles.hint}> · {formatRate(stage.rate)}</span>}</span></span>
                <span className={o.bar} aria-hidden="true"><span className={o.barFill} style={{ width: `${top ? (stage.count / top) * 100 : 0}%` }} /></span>
              </li>
            ))}
          </ol>
        </section>

        <section className={styles.card} aria-labelledby="reminder-title">
          <div className={o.sectionHeading}><h2 id="reminder-title" className={styles.cardTitle}>今天需要處理</h2>{activeReminders.length > 0 && <Tag tone="warning">{activeReminders.reduce((total, item) => total + item.count, 0)} 件</Tag>}</div>
          {activeReminders.length > 0 ? (
            <ul className={o.reminders}>
              {[...activeReminders].sort((a, b) => (a.kind === "pending_review" ? -1 : b.kind === "pending_review" ? 1 : b.count - a.count)).map((reminder) => (
                <li key={reminder.kind}><Link to={REMINDER_LINKS[reminder.kind] ?? "/cases"} className={o.reminder}><span>{reminder.label}</span><Tag tone="warning">{reminder.count}</Tag></Link></li>
              ))}
            </ul>
          ) : <p className={o.completed}>今天沒有待處理事項 ✓</p>}
          {completedReminderCount > 0 && <p className={o.completed}>其餘待辦皆已完成 ✓</p>}
          <Link to={REMINDER_LINKS.pending_review ?? "/recommendations?status=pending_review"} className={o.primaryAction}>開始今日審核 <span aria-hidden="true">→</span></Link>
        </section>
      </div>

      <section aria-labelledby="inventory-title">
        <h2 id="inventory-title" className={o.sectionTitle}>名單概況</h2>
        <div className={o.inventory}>{inventoryKpis.map((kpi) => <KpiLink key={kpi.label} {...kpi} compact />)}</div>
      </section>

      {data.by_source.length >= 2 && (
        <section className={styles.card} aria-labelledby="source-title">
          <div className={o.sectionHeading}>
            <div>
              <h2 id="source-title" className={styles.cardTitle}>來源成效</h2>
              <span className={styles.hint}>依回覆率排序</span>
            </div>
            {data.by_source.length > 5 && (
              <Button
                variant="ghost"
                size="sm"
                aria-expanded={sourceExpanded}
                aria-controls="source-performance-table"
                onClick={() => setSourceExpanded((expanded) => !expanded)}
              >
                {sourceExpanded ? "收起來源" : "查看全部來源"}
              </Button>
            )}
          </div>
          <div id="source-performance-table" className={styles.tableWrap}>
            <table className={styles.table}><thead><tr><th>資料來源</th><th>寄出</th><th>回覆</th><th>回覆率</th></tr></thead><tbody>
              {visibleSources.map((source) => <tr key={source.source}><td>{source.source}</td><td>{source.sent}</td><td>{source.replied}</td><td>{source.insufficient ? <Tag tone="neutral">樣本不足</Tag> : formatRate(source.reply_rate)}</td></tr>)}
            </tbody></table>
          </div>
        </section>
      )}
    </>
  );
}

function formatSigned(value: number, suffix = ""): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString("zh-TW", { maximumFractionDigits: 1 })}${suffix}`;
}

function KpiLink({ label, value, hint, insight, to, compact = false, featured = false }: { label: string; value: string | number; hint: string; insight?: string; to: string; compact?: boolean; featured?: boolean }) {
  return <Link to={to} className={`${o.kpi} ${compact ? o.compactKpi : ""} ${featured ? o.featuredKpi : ""}`}>
    <span className={styles.countLabel}>{label}</span>
    <strong className={o.kpiValue}>{typeof value === "number" ? value.toLocaleString("zh-TW") : value}</strong>
    {insight && <span className={o.kpiInsight}>{insight}</span>}
    <span className={o.kpiHint}>→ {hint}</span>
  </Link>;
}
