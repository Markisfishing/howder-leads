import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useCampaigns } from "../../api/hooks";
import type { Campaign, CampaignProgress } from "../../api/types";
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

/** 「我的待辦」：還有草稿要審（待審核、失敗），或都審完等著按寄出（待寄出，M2-16） */
export function needsAction(campaign: Campaign): boolean {
  return campaign.progress.pending_review > 0 || campaign.progress.failed > 0 || campaign.status === "ready";
}

/** 邀請信批次列表（SPEC 6.2 /campaigns · M2-03e） */
export function CampaignsPage() {
  const { data, isLoading, error, refetch } = useCampaigns();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [view, setView] = useState<"todo" | "active" | "done" | "all">("todo");
  const filtered = useMemo(() => (data ?? []).filter((campaign) => {
    const term = search.trim().toLowerCase();
    const matchesSearch = !term || `${campaign.name} ${campaign.owner_name ?? ""} ${campaign.template_name ?? ""}`.toLowerCase().includes(term);
    const matchesView = view === "all" || (view === "done" ? campaign.status === "done" : view === "active" ? campaign.status !== "done" : needsAction(campaign));
    return matchesSearch && matchesView;
  }), [data, search, view]);
  const todoCount = (data ?? []).filter(needsAction).length;
  const activeCount = (data ?? []).filter((campaign) => campaign.status !== "done").length;
  const doneCount = (data ?? []).filter((campaign) => campaign.status === "done").length;

  return (
    <>
      <header className={styles.head}>
        <div className={c.headRow}>
          <h1 className={styles.title}>邀請信</h1>
          <Button variant="primary" onClick={() => navigate("/campaigns/new")}>
            建立邀請信批次
          </Button>
        </div>
      </header>
      <MailConnectionBanner />

      <section className={styles.card} aria-labelledby="campaign-list-title">
        <div className={c.listHeader}><h2 id="campaign-list-title" className={styles.cardTitle}>邀請信批次</h2><span className={styles.hint}>{filtered.length} 筆</span></div>
        <div className={c.draftToolbar}>
          <label className={c.searchField}><span className="visually-hidden">搜尋批次、負責人或模板</span><span aria-hidden="true">⌕</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜尋批次、負責人或模板" /></label>
          <nav className={c.statusTabs} aria-label="邀請信工作檢視">
            <CampaignViewButton active={view === "todo"} count={todoCount} onClick={() => setView("todo")}>我的待辦</CampaignViewButton>
            <CampaignViewButton active={view === "active"} count={activeCount} onClick={() => setView("active")}>進行中</CampaignViewButton>
            <CampaignViewButton active={view === "done"} count={doneCount} onClick={() => setView("done")}>最近完成</CampaignViewButton>
            <CampaignViewButton active={view === "all"} count={data?.length ?? 0} onClick={() => setView("all")}>全部</CampaignViewButton>
          </nav>
        </div>
        {isLoading ? (
          <Loading />
        ) : error ? (
          <ErrorState error={error} onRetry={() => void refetch()} />
        ) : !data || data.length === 0 ? (
          <Empty title="還沒有邀請信批次">按「建立邀請信批次」，從已通過的公司裡挑選要寄的對象。</Empty>
        ) : filtered.length === 0 ? (
          <Empty title="找不到符合條件的批次">請換一個搜尋字詞或工作檢視。</Empty>
        ) : (
          <ul className={c.list}>
            {filtered.map((cp) => (
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

function CampaignViewButton({ active, count, onClick, children }: { active: boolean; count: number; onClick: () => void; children: string }) {
  return <button type="button" aria-pressed={active} onClick={onClick}>{children} <strong>{count}</strong></button>;
}
