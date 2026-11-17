import { Link, useNavigate } from "react-router-dom";

import { useCampaigns } from "../../api/hooks";
import type { CampaignProgress } from "../../api/types";
import { Button } from "../../components/Button";
import { Empty, ErrorState, Loading } from "../../components/StateView";
import { Tag } from "../../components/Tag";
import { CAMPAIGN_STATUS_LABELS, CAMPAIGN_STATUS_TONE, formatDateTime } from "../../lib/labels";
import styles from "../Page.module.css";
import c from "./Campaigns.module.css";
import { MailConnectionBanner } from "./MailConnectionBanner";

/** 一行進度文字，例如「共 10 封：待審核 3、已核准 5、已寄出 2」；0 的項目不顯示 */
export function progressText(p: CampaignProgress): string {
  const parts: [string, number][] = [
    ["產生中", p.generating],
    ["待審核", p.pending_review],
    ["已核准", p.approved],
    ["已排程", p.scheduled],
    ["已寄出", p.sent],
    ["失敗", p.failed],
    ["已丟棄", p.discarded],
  ];
  const shown = parts.filter(([, n]) => n > 0).map(([label, n]) => `${label} ${n}`);
  return `共 ${p.total} 封${shown.length ? "：" + shown.join("、") : ""}`;
}

/** 邀請信批次列表（SPEC 6.2 /campaigns · M2-03e） */
export function CampaignsPage() {
  const { data, isLoading, error, refetch } = useCampaigns();
  const navigate = useNavigate();

  return (
    <>
      <header className={styles.head}>
        <div className={c.headRow}>
          <h1 className={styles.title}>邀請信</h1>
          <Button variant="primary" onClick={() => navigate("/campaigns/new")}>
            建立邀請信批次
          </Button>
        </div>
        <p className={styles.meta}>從已通過的公司產生草稿，逐封確認、核准後才會寄出。系統不會自動寄信。</p>
      </header>
      <MailConnectionBanner />

      <section className={styles.card} aria-labelledby="campaign-list-title">
        <h2 id="campaign-list-title" className={styles.cardTitle}>
          我的批次
        </h2>
        {isLoading ? (
          <Loading />
        ) : error ? (
          <ErrorState error={error} onRetry={() => void refetch()} />
        ) : !data || data.length === 0 ? (
          <Empty title="還沒有邀請信批次">按「建立邀請信批次」，從已通過的公司裡挑選要寄的對象。</Empty>
        ) : (
          <ul className={c.list}>
            {data.map((cp) => (
              <li key={cp.campaign_id}>
                <Link to={`/campaigns/${cp.campaign_id}`} className={c.item}>
                  <span>
                    <span className={c.itemName}>
                      {cp.name}
                      <Tag tone={CAMPAIGN_STATUS_TONE[cp.status]}>{CAMPAIGN_STATUS_LABELS[cp.status]}</Tag>
                    </span>
                    <span className={c.progressText}>{progressText(cp.progress)}</span>
                  </span>
                  <span className={c.progressText}>
                    {cp.owner_name} · {formatDateTime(cp.created_at)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
