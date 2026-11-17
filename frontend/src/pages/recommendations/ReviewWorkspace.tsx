import { useEffect, useMemo, useState } from "react";

import { useClaim } from "../../api/hooks";
import type { CompanyRow } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { Button } from "../../components/Button";
import { Stars } from "../../components/Stars";
import { Tag } from "../../components/Tag";
import { hostname } from "../../lib/labels";
import styles from "./ReviewWorkspace.module.css";

interface Props {
  rows: CompanyRow[];
  currentIndex: number;
  onIndexChange: (index: number) => void;
  onApprove: (company: CompanyRow) => void;
  onReject: (company: CompanyRow) => void;
  onSnooze: (company: CompanyRow) => void;
  onOpenDetails: (company: CompanyRow) => void;
  snoozedCount: number;
  busy?: boolean;
}

/** 單筆審核工作台：只保留判斷一家公司所需的資訊與三個核心動作。 */
export function ReviewWorkspace({
  rows,
  currentIndex,
  onIndexChange,
  onApprove,
  onReject,
  onSnooze,
  onOpenDetails,
  snoozedCount,
  busy = false,
}: Props) {
  const { user } = useAuth();
  const claim = useClaim();
  const [showEvidence, setShowEvidence] = useState(false);
  const company = rows[currentIndex] ?? null;
  const total = rows.length;
  const currentNumber = company ? currentIndex + 1 : 0;
  const canGoPrevious = currentIndex > 0;
  const canGoNext = currentIndex < total - 1;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, select, textarea, button, [contenteditable='true']")) return;
      if (!company) return;
      if (event.key.toLowerCase() === "a") {
        event.preventDefault();
        onApprove(company);
      } else if (event.key.toLowerCase() === "r") {
        event.preventDefault();
        onReject(company);
      } else if (event.key.toLowerCase() === "s") {
        event.preventDefault();
        onSnooze(company);
      } else if (event.key.toLowerCase() === "j") {
        event.preventDefault();
        onIndexChange(Math.min(currentIndex + 1, Math.max(total - 1, 0)));
      } else if (event.key.toLowerCase() === "k") {
        event.preventDefault();
        onIndexChange(Math.max(currentIndex - 1, 0));
      } else if (event.code === "Space") {
        event.preventDefault();
        setShowEvidence((value) => !value);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [company, currentIndex, onApprove, onIndexChange, onReject, onSnooze, total]);

  const evidenceTags = useMemo(() => company?.tags ?? [], [company?.tags]);

  if (!company) {
    return (
      <section className={styles.empty} aria-live="polite">
        <span className={styles.emptyIcon} aria-hidden="true">✓</span>
        <h2>今日待審工作已完成</h2>
        <p>目前沒有符合條件的待審公司，可以切換到完整清單繼續查詢。</p>
      </section>
    );
  }

  const claimCompany = () => {
    if (company.owner_id === user?.user_id) return;
    claim.mutate(company.company_id);
  };

  return (
    <section className={styles.workspace} aria-label="單筆審核工作台">
      <aside className={styles.queue} aria-label="工作佇列">
        <div className={styles.queueHead}>
          <span className={styles.queueTitle}>工作佇列</span>
        </div>
        <button type="button" className={`${styles.queueItem} ${styles.queueActive}`} aria-current="true">
          <span className={styles.queueDot} aria-hidden="true">●</span>
          <span>待審</span>
          <strong>{total}</strong>
        </button>
        <div className={styles.queueItem}>
          <span className={styles.queueDotMuted} aria-hidden="true">○</span>
          <span>稍後</span>
          <strong>{snoozedCount}</strong>
        </div>
      </aside>

      <div className={styles.reviewPane}>
        <header className={styles.reviewNav}>
          <button
            type="button"
            className={styles.navButton}
            disabled={!canGoPrevious}
            onClick={() => onIndexChange(currentIndex - 1)}
          >
            ← 上一筆
          </button>
          <span className={styles.position} aria-live="polite">
            待審 {currentNumber} / {total}
          </span>
          <button
            type="button"
            className={styles.navButton}
            disabled={!canGoNext}
            onClick={() => onIndexChange(currentIndex + 1)}
          >
            下一筆 →
          </button>
          <details className={styles.shortcutMenu}>
            <summary aria-label="鍵盤快捷鍵">?</summary>
            <div>J / K 上一筆／下一筆 · A 通過 · R 排除 · S 稍後 · Space 查看依據</div>
          </details>
        </header>

        <article className={styles.card} aria-labelledby="review-company-title">
          <div className={styles.companyHead}>
            <div className={styles.companyIdentity}>
              <Stars stars={company.stars} priority={company.priority} fitStars={company.fit_stars} />
              <h2 id="review-company-title">{company.name}</h2>
              <p className={styles.companyMeta}>
                {company.industry ?? "產業未分類"} · {company.country || "國別未標示"}
              </p>
              {company.website_url ? (
                <a href={company.website_url} target="_blank" rel="noreferrer noopener" className={styles.website}>
                  {hostname(company.website_url)} ↗
                </a>
              ) : (
                <span className={styles.muted}>無官網</span>
              )}
            </div>
          </div>

          <section className={styles.reason} aria-labelledby="review-reason-title">
            <h3 id="review-reason-title">推薦理由</h3>
            <p>{company.reason ?? "模型沒有提供推薦理由，請查看完整資料後判斷。"}</p>
          </section>

          <button
            type="button"
            className={styles.evidenceToggle}
            aria-expanded={showEvidence}
            onClick={() => setShowEvidence((value) => !value)}
          >
            {showEvidence ? "收合依據" : "查看更多依據"}
            <span aria-hidden="true">{showEvidence ? " ↑" : " ↓"}</span>
          </button>

          {showEvidence && (
            <section className={styles.evidence} aria-label="完整推薦依據">
              <dl className={styles.evidenceGrid}>
                <div>
                  <dt>產品類型</dt>
                  <dd>{company.product_type ?? "未標示"}</dd>
                </div>
                <div>
                  <dt>命中標籤</dt>
                  <dd className={styles.tagList}>
                    {evidenceTags.length > 0 ? evidenceTags.map((tag) => <Tag key={tag}>{tag}</Tag>) : "未標示"}
                  </dd>
                </div>
                <div>
                  <dt>資料來源</dt>
                  <dd>{company.source ?? "未標示"}</dd>
                </div>
                <div>
                  <dt>網址狀態</dt>
                  <dd>{company.url_status === "valid" ? "有效" : company.url_status === "invalid" ? "無效" : "未檢查"}</dd>
                </div>
                <div>
                  <dt>使用可能性</dt>
                  <dd>{company.likelihood ?? "未評估"}</dd>
                </div>
                <div className={styles.fullWidth}>
                  <dt>完整推薦理由</dt>
                  <dd>{company.reason ?? "未提供"}</dd>
                </div>
              </dl>
              <Button size="sm" onClick={() => onOpenDetails(company)}>
                開啟完整資料、修改與審核紀錄
              </Button>
            </section>
          )}

          <div className={styles.ownerRow}>
            <span>負責人：{company.owner_name ?? "未指派"}</span>
            {company.owner_id === user?.user_id ? (
              <Tag tone="success">已指派給我</Tag>
            ) : (
              <Button size="sm" busy={claim.isPending} onClick={claimCompany}>
                指派給我
              </Button>
            )}
          </div>
        </article>

        <footer className={styles.actions} aria-label="審核操作">
          <Button variant="danger" disabled={busy} onClick={() => onReject(company)}>
            排除 <kbd>R</kbd>
          </Button>
          <Button disabled={busy} onClick={() => onSnooze(company)}>
            稍後 <kbd>S</kbd>
          </Button>
          <Button variant="primary" busy={busy} onClick={() => onApprove(company)}>
            通過並下一筆 <kbd>A</kbd>
          </Button>
        </footer>
      </div>
    </section>
  );
}
