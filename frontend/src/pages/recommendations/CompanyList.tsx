import type { ReactNode } from "react";

import type { CompanyRow } from "../../api/types";
import { Stars } from "../../components/Stars";
import { Tag } from "../../components/Tag";
import { COLUMN_LABELS, type ColumnKey, DEFAULT_COLUMNS } from "../../lib/columns";
import { LIKELIHOOD_TONE, STATUS_LABELS, STATUS_TONE, formatDateTime, hostname } from "../../lib/labels";
import styles from "./Recommendations.module.css";

interface Props {
  rows: CompanyRow[];
  selected: Set<number>;
  onToggle: (id: number) => void;
  onToggleAll: (checked: boolean) => void;
  onOpen: (id: number) => void;
  /** 欄位自選（M3-13b）；沒給就用預設欄位 */
  columns?: ColumnKey[];
}

const URL_STATUS_LABELS = { valid: "有效", invalid: "無效", unchecked: "未檢查" } as const;

/** 放在公司名稱下面那一行的欄位（其他欄位有自己的格子） */
const META_COLUMNS: ColumnKey[] = [
  "tax_id",
  "industry",
  "product_type",
  "website_url",
  "url_status",
  "country",
  "source",
  "customer_type",
  "score",
  "updated_at",
];

function metaValue(c: CompanyRow, key: ColumnKey): ReactNode {
  switch (key) {
    case "tax_id":
      return <span className="mono">{c.tax_id}</span>;
    case "industry":
      return c.industry ?? "產業未分類";
    case "website_url":
      return c.website_url ? (
        <a href={c.website_url} target="_blank" rel="noreferrer noopener">
          {hostname(c.website_url)}
        </a>
      ) : (
        "無官網"
      );
    case "url_status":
      return `網址${URL_STATUS_LABELS[c.url_status]}`;
    case "updated_at":
      return `更新 ${formatDateTime(c.updated_at)}`;
    case "product_type":
    case "country":
    case "source":
    case "customer_type":
    case "score": {
      const v = c[key];
      return v ? `${COLUMN_LABELS[key]} ${v}` : null;
    }
    default:
      return null;
  }
}

/** 區塊：推薦清單 · 手機是卡片、768px 以上是表格列（F-REC-1、F-REC-8 欄位自選） */
export function CompanyList({ rows, selected, onToggle, onToggleAll, onOpen, columns = DEFAULT_COLUMNS }: Props) {
  const allChecked = rows.length > 0 && rows.every((r) => selected.has(r.company_id));
  const show = (k: ColumnKey) => columns.includes(k);
  const meta = META_COLUMNS.filter(show);

  return (
    <section className={styles.list} aria-label="推薦公司">
      <div className={styles.listHead}>
        <input
          type="checkbox"
          className={styles.check}
          checked={allChecked}
          onChange={(e) => onToggleAll(e.target.checked)}
          aria-label="全選這一頁"
        />
        <span>{show("fit_stars") ? "推薦度" : ""}</span>
        <span>公司{show("reason") && "／推薦理由"}</span>
        <span>{show("likelihood") ? "使用可能性" : ""}</span>
        <span>{[show("status") && "狀態", show("owner_name") && "負責人"].filter(Boolean).join("／")}</span>
      </div>

      {rows.map((c) => {
        const isSelected = selected.has(c.company_id);
        const metaParts = meta.map((k) => [k, metaValue(c, k)] as const).filter(([, v]) => v !== null);
        return (
          <article key={c.company_id} className={`${styles.row} ${isSelected ? styles.selected : ""}`}>
            <input
              type="checkbox"
              className={`${styles.check} ${styles.rowCheck}`}
              checked={isSelected}
              onChange={() => onToggle(c.company_id)}
              aria-label={`選取 ${c.name}`}
            />
            <div className={styles.rowStars}>
              {show("fit_stars") && <Stars stars={c.stars} priority={c.priority} fitStars={c.fit_stars} />}
            </div>
            <div className={styles.rowCompany}>
              <button type="button" className={styles.rowName} onClick={() => onOpen(c.company_id)}>
                {c.name}
              </button>
              {(metaParts.length > 0 || c.added_manually) && (
                <p className={styles.rowMeta}>
                  {metaParts.map(([k, v], i) => (
                    <span key={k}>
                      {i > 0 && " · "}
                      {v}
                    </span>
                  ))}
                  {c.added_manually && `${metaParts.length ? " · " : ""}手動加入`}
                </p>
              )}
              {show("tags") && c.tags.length > 0 && (
                <p className={styles.rowTags}>
                  {c.tags.map((t) => (
                    <Tag key={t} tone="neutral">
                      {t}
                    </Tag>
                  ))}
                </p>
              )}
            </div>
            {show("reason") && <p className={styles.rowReason}>{c.reason ?? "—"}</p>}
            <div className={styles.rowLikely}>
              {show("likelihood") && c.likelihood ? (
                <Tag tone={LIKELIHOOD_TONE[c.likelihood]}>
                  <span className={styles.mobileOnly}>使用可能性：</span>
                  {c.likelihood}
                </Tag>
              ) : null}
              {c.is_competitor && <Tag tone="warning">競合</Tag>}
            </div>
            <div className={styles.rowStatus}>
              {show("status") && <Tag tone={STATUS_TONE[c.status]}>{STATUS_LABELS[c.status]}</Tag>}
              {show("owner_name") && c.owner_name && <span className={styles.owner}>{c.owner_name}</span>}
            </div>
          </article>
        );
      })}
    </section>
  );
}
