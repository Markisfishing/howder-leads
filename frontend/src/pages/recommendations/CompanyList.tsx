import type { CompanyRow } from "../../api/types";
import { Stars } from "../../components/Stars";
import { Tag } from "../../components/Tag";
import { LIKELIHOOD_TONE, STATUS_LABELS, STATUS_TONE, hostname } from "../../lib/labels";
import styles from "./Recommendations.module.css";

interface Props {
  rows: CompanyRow[];
  selected: Set<number>;
  onToggle: (id: number) => void;
  onToggleAll: (checked: boolean) => void;
  onOpen: (id: number) => void;
}

/** 區塊：推薦清單 · 手機是卡片、768px 以上是表格列（F-REC-1） */
export function CompanyList({ rows, selected, onToggle, onToggleAll, onOpen }: Props) {
  const allChecked = rows.length > 0 && rows.every((r) => selected.has(r.company_id));

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
        <span>推薦度</span>
        <span>公司／推薦理由</span>
        <span>使用可能性</span>
        <span>狀態／負責人</span>
      </div>

      {rows.map((c) => {
        const isSelected = selected.has(c.company_id);
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
              <Stars stars={c.stars} priority={c.priority} />
            </div>
            <div className={styles.rowCompany}>
              <button type="button" className={styles.rowName} onClick={() => onOpen(c.company_id)}>
                {c.name}
              </button>
              <p className={styles.rowMeta}>
                {c.industry ?? "產業未分類"}
                {" · "}
                {c.website_url ? (
                  <a href={c.website_url} target="_blank" rel="noreferrer noopener">
                    {hostname(c.website_url)}
                  </a>
                ) : (
                  <span>無官網</span>
                )}
                {c.added_manually && " · 手動加入"}
              </p>
            </div>
            <p className={styles.rowReason}>{c.reason ?? "—"}</p>
            <div className={styles.rowLikely}>
              {c.likelihood ? (
                <Tag tone={LIKELIHOOD_TONE[c.likelihood]}>
                  <span className={styles.mobileOnly}>使用可能性：</span>
                  {c.likelihood}
                </Tag>
              ) : null}
              {c.is_competitor && <Tag tone="warning">競合</Tag>}
            </div>
            <div className={styles.rowStatus}>
              <Tag tone={STATUS_TONE[c.status]}>{STATUS_LABELS[c.status]}</Tag>
              {c.owner_name && <span className={styles.owner}>{c.owner_name}</span>}
            </div>
          </article>
        );
      })}
    </section>
  );
}
