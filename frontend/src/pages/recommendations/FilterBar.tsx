import { useEffect, useState } from "react";

import { useDimensions } from "../../api/hooks";
import type { ListFilters, SortKey, UrlStatus } from "../../lib/filters";
import { STATUS_LABELS } from "../../lib/labels";
import styles from "./Recommendations.module.css";

interface Props {
  filters: ListFilters;
  onChange: (patch: Partial<ListFilters>) => void;
}

export const STAR_OPTIONS = [
  { value: "5", label: "★★★★★ 第一優先" },
  { value: "4", label: "★★★★ 可開發" },
  { value: "2", label: "★★ 觀察／策略" },
  { value: "1", label: "★ 暫不優先" },
  { value: "0", label: "未評分（手動加入）" },
];
const MIN_STAR_OPTIONS = [4.5, 4, 3.5, 3, 2];

/** 區塊：篩選列 · 條件同步到網址（F-REC-2） */
export function FilterBar({ filters, onChange }: Props) {
  const { data: dims } = useDimensions();
  const [q, setQ] = useState(filters.q);
  const [product, setProduct] = useState(filters.productType);

  // 打字停 300ms 才更新網址與查詢，避免每打一個字就查一次
  useEffect(() => {
    if (q === filters.q) return;
    const t = setTimeout(() => onChange({ q }), 300);
    return () => clearTimeout(t);
  }, [q, filters.q, onChange]);
  useEffect(() => {
    if (product === filters.productType) return;
    const t = setTimeout(() => onChange({ productType: product }), 300);
    return () => clearTimeout(t);
  }, [product, filters.productType, onChange]);

  const triState = (v: boolean | null) => (v === null ? "" : String(v));
  const fromTriState = (v: string) => (v === "" ? null : v === "true");

  return (
    <section className={styles.filters} aria-label="篩選">
      <label className={`${styles.field} ${styles.fieldWide}`}>
        <span className={styles.fieldLabel}>搜尋</span>
        <input
          className={styles.input}
          type="search"
          placeholder="公司名稱或統編"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>星級</span>
        <select
          className={styles.input}
          value={filters.stars.length === 1 ? String(filters.stars[0]) : ""}
          onChange={(e) => onChange({ stars: e.target.value === "" ? [] : [Number(e.target.value)] })}
        >
          <option value="">全部</option>
          {STAR_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>產業</span>
        <select
          className={styles.input}
          value={filters.industryId ?? ""}
          onChange={(e) => onChange({ industryId: e.target.value ? Number(e.target.value) : null })}
        >
          <option value="">全部產業</option>
          {dims?.industries.map((i) => (
            <option key={i.industry_id} value={i.industry_id}>
              {i.name}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>狀態</span>
        <select
          className={styles.input}
          value={filters.status.length === 1 ? filters.status[0] : ""}
          onChange={(e) => onChange({ status: e.target.value ? [e.target.value] : [] })}
        >
          <option value="">全部狀態</option>
          {(["pending_review", "approved", "rejected", "sent", "replied", "do_not_contact"] as const).map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>負責人</span>
        <select
          className={styles.input}
          value={filters.owner ?? ""}
          onChange={(e) => onChange({ owner: e.target.value || null })}
        >
          <option value="">全部</option>
          <option value="me">我負責的</option>
          <option value="none">還沒有人負責</option>
          {dims?.users.map((u) => (
            <option key={u.user_id} value={String(u.user_id)}>
              {u.display_name}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>官網</span>
        <select
          className={styles.input}
          value={triState(filters.hasWebsite)}
          onChange={(e) => onChange({ hasWebsite: fromTriState(e.target.value) })}
        >
          <option value="">不限</option>
          <option value="true">有官網</option>
          <option value="false">沒有官網</option>
        </select>
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>競合</span>
        <select
          className={styles.input}
          value={triState(filters.competitor)}
          onChange={(e) => onChange({ competitor: fromTriState(e.target.value) })}
        >
          <option value="">不限</option>
          <option value="false">排除競合對象</option>
          <option value="true">只看競合對象</option>
        </select>
      </label>
      {/* M3-06c：CSV v1 欄位的篩選（F-REC-7） */}
      <label className={styles.field}>
        <span className={styles.fieldLabel}>星等下限</span>
        <select
          className={styles.input}
          value={filters.minStars ?? ""}
          onChange={(e) => onChange({ minStars: e.target.value === "" ? null : Number(e.target.value) })}
        >
          <option value="">不限</option>
          {MIN_STAR_OPTIONS.map((v) => (
            <option key={v} value={v}>
              {v.toFixed(1)} 星以上
            </option>
          ))}
        </select>
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>國別</span>
        <select
          className={styles.input}
          value={filters.country ?? ""}
          onChange={(e) => onChange({ country: e.target.value || null })}
        >
          <option value="">全部國別</option>
          {dims?.countries.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>資料來源</span>
        <select
          className={styles.input}
          value={filters.source ?? ""}
          onChange={(e) => onChange({ source: e.target.value || null })}
        >
          <option value="">全部來源</option>
          {dims?.sources.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
          <option value="none">未標示</option>
        </select>
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>網址狀態</span>
        <select
          className={styles.input}
          value={filters.urlStatus ?? ""}
          onChange={(e) => onChange({ urlStatus: (e.target.value || null) as UrlStatus | null })}
        >
          <option value="">不限</option>
          <option value="valid">有效</option>
          <option value="unchecked">未檢查</option>
          <option value="invalid">無效</option>
        </select>
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>命中標籤</span>
        <select
          className={styles.input}
          value={filters.tag ?? ""}
          onChange={(e) => onChange({ tag: e.target.value || null })}
        >
          <option value="">全部標籤</option>
          {dims?.tags.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>產品類型</span>
        <input
          className={styles.input}
          type="search"
          placeholder="例如 控制盤"
          value={product}
          onChange={(e) => setProduct(e.target.value)}
        />
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>排序</span>
        <select
          className={styles.input}
          value={filters.sort}
          onChange={(e) => onChange({ sort: e.target.value as SortKey })}
        >
          <option value="recommended">推薦度</option>
          <option value="name">公司名稱</option>
          <option value="updated">最近更新</option>
        </select>
      </label>
    </section>
  );
}
