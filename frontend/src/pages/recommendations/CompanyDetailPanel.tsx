import { useState } from "react";
import { Link } from "react-router-dom";

import { useClaim, useCompany, useDimensions, usePatchCompany, useRelease, useReview } from "../../api/hooks";
import type { CompanyDetail } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { Button } from "../../components/Button";
import { Stars } from "../../components/Stars";
import { ErrorState, InlineError, Loading } from "../../components/StateView";
import { Tag } from "../../components/Tag";
import {
  ACTIVITY_LABELS,
  LIKELIHOOD_TONE,
  REJECT_REASON_LABELS,
  STATUS_LABELS,
  STATUS_TONE,
  activityNote,
  formatDate,
  formatDateTime,
  hostname,
} from "../../lib/labels";
import { isLockedByOther } from "../../lib/ownership";
import styles from "./CompanyDetail.module.css";
import { ContactsSection } from "./ContactsSection";
import { SiteSummarySection } from "./SiteSummarySection";
import { RejectDialog } from "./RejectDialog";

/** 區塊：公司詳情 · 完整理由、官網、登記產品、往來紀錄；可修正官網與產業（F-REC-4） */
export function CompanyDetailPanel({ companyId, showPageLink = false }: { companyId: number; showPageLink?: boolean }) {
  const { data, isLoading, error, refetch } = useCompany(companyId);
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorState error={error} onRetry={() => void refetch()} />;
  return <Detail company={data} showPageLink={showPageLink} />;
}

function Detail({ company: c, showPageLink }: { company: CompanyDetail; showPageLink: boolean }) {
  const { user, isManager } = useAuth();
  const { data: dims } = useDimensions();
  const review = useReview();
  const claim = useClaim();
  const release = useRelease();
  const patch = usePatchCompany();
  const [rejectOpen, setRejectOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [website, setWebsite] = useState(c.website_url ?? "");
  const [industryId, setIndustryId] = useState(c.industry_id ? String(c.industry_id) : "");
  const [note, setNote] = useState("");

  // 打開詳情的時間點；只用來決定按鈕狀態，送出後後端會再檢查一次
  const [openedAt] = useState(() => Date.now());
  const lockedByOther = isLockedByOther(c, user?.user_id, openedAt);
  const canAct = !lockedByOther || isManager;
  const canApprove = ["pending_review", "rejected"].includes(c.status);
  const canReject = ["pending_review", "approved"].includes(c.status);
  const modelIndustry = dims?.industries.find((i) => i.industry_id === c.model_industry_id)?.name;

  const saveEdits = () => {
    const body: Parameters<typeof patch.mutate>[0]["body"] = {};
    const trimmed = website.trim();
    if (trimmed !== (c.website_url ?? "")) {
      if (trimmed) body.website_url = trimmed;
      else body.clear_website = true;
    }
    if (industryId && Number(industryId) !== c.industry_id) body.industry_id = Number(industryId);
    if (note.trim()) body.note = note.trim();
    if (Object.keys(body).length === 0) {
      setEditing(false);
      return;
    }
    patch.mutate(
      { id: c.company_id, body },
      {
        onSuccess: () => {
          setEditing(false);
          setNote("");
        },
      },
    );
  };

  const actionError = review.error ?? claim.error ?? release.error;

  return (
    <div className={styles.detail}>
      <section className={styles.summary}>
        <div className={styles.titleRow}>
          <Stars stars={c.stars} priority={c.priority} />
          <Tag tone={STATUS_TONE[c.status]}>{STATUS_LABELS[c.status]}</Tag>
          {c.likelihood && <Tag tone={LIKELIHOOD_TONE[c.likelihood]}>使用可能性：{c.likelihood}</Tag>}
          {c.is_competitor && <Tag tone="warning">競合對象</Tag>}
          {c.added_manually && <Tag tone="info">手動加入</Tag>}
        </div>
        <p className={styles.meta}>
          統編 <span className="mono">{c.tax_id}</span>
          {c.run_id && <> · 匯入批次 #{c.run_id}</>}
          {showPageLink && (
            <>
              {" · "}
              <Link to={`/companies/${c.company_id}`}>開成完整頁面</Link>
            </>
          )}
        </p>
      </section>

      {/* 區塊：主要動作 */}
      <section className={styles.actions} aria-label="操作">
        {canApprove && (
          <Button
            variant="primary"
            disabled={!canAct}
            busy={review.isPending}
            onClick={() => review.mutate({ company_ids: [c.company_id], decision: "approved" })}
          >
            通過
          </Button>
        )}
        {canReject && (
          <Button variant="danger" disabled={!canAct} onClick={() => setRejectOpen(true)}>
            排除…
          </Button>
        )}
        {c.owner_id === user?.user_id ? (
          <Button busy={release.isPending} onClick={() => release.mutate(c.company_id)}>
            釋出
          </Button>
        ) : (
          <Button disabled={!canAct} busy={claim.isPending} onClick={() => claim.mutate(c.company_id)}>
            {c.owner_id ? "改由我負責" : "認領"}
          </Button>
        )}
        {!editing && (
          <Button disabled={!canAct} onClick={() => setEditing(true)}>
            修正資料
          </Button>
        )}
      </section>
      <p className={styles.owner}>
        負責業務：{c.owner_name ?? "還沒有人負責"}
        {c.owner_locked_until && <>（鎖定到 {formatDate(c.owner_locked_until)}）</>}
        {lockedByOther && !isManager && <>，只有負責業務或主管可以修改</>}
      </p>
      <InlineError error={actionError} />

      {/* 區塊：推薦理由 */}
      <section className={styles.block}>
        <h3 className={styles.blockTitle}>推薦理由</h3>
        <p>{c.reason ?? "匯入資料沒有提供推薦理由"}</p>
        {c.priority_definition && (
          <p className={styles.hint}>
            {c.priority} {c.priority_label}：{c.priority_definition}（建議：{c.suggested_action}）
          </p>
        )}
      </section>

      {/* 區塊：基本資料（可修正） */}
      <section className={styles.block}>
        <h3 className={styles.blockTitle}>基本資料</h3>
        {editing ? (
          <div className={styles.form}>
            <label className={styles.field}>
              <span className={styles.label}>官網（清空 = 沒有官網）</span>
              <input
                className={styles.input}
                type="url"
                value={website}
                onChange={(e) => setWebsite(e.target.value)}
                placeholder="https://"
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>產業</span>
              <select className={styles.input} value={industryId} onChange={(e) => setIndustryId(e.target.value)}>
                <option value="">未分類</option>
                {dims?.industries.map((i) => (
                  <option key={i.industry_id} value={i.industry_id}>
                    {i.name}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              <span className={styles.label}>備註（選填）</span>
              <textarea className={styles.input} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
            </label>
            <div className={styles.formActions}>
              <Button onClick={() => setEditing(false)}>取消</Button>
              <Button variant="primary" busy={patch.isPending} onClick={saveEdits}>
                儲存
              </Button>
            </div>
            <InlineError error={patch.error} />
          </div>
        ) : (
          <dl className={styles.facts}>
            <div>
              <dt>官網</dt>
              <dd>
                {c.website_url ? (
                  <a href={c.website_url} target="_blank" rel="noreferrer noopener">
                    {hostname(c.website_url)}
                  </a>
                ) : (
                  "無"
                )}
                {c.website_verified && <span className={styles.verified}>（業務已確認）</span>}
              </dd>
            </div>
            <div>
              <dt>產業</dt>
              <dd>
                {c.industry ?? "未分類"}
                {c.model_industry_id !== null && c.model_industry_id !== c.industry_id && (
                  <span className={styles.verified}>（匯入時的產業：{modelIndustry ?? "—"}）</span>
                )}
              </dd>
            </div>
            <div>
              <dt>客戶屬性</dt>
              <dd>{c.customer_type ?? "—"}</dd>
            </div>
            <div>
              <dt>登記產品</dt>
              <dd>{c.registered_products ?? "—"}</dd>
            </div>
          </dl>
        )}
      </section>

      {/* 區塊：官網摘要（M4-08e） */}
      <SiteSummarySection company={c} canAct={canAct} />

      {/* 區塊：聯絡人（M2-01b） */}
      <ContactsSection company={c} canAct={canAct} isManager={isManager} />

      {/* 區塊：審核紀錄 */}
      {c.reviews.length > 0 && (
        <section className={styles.block}>
          <h3 className={styles.blockTitle}>審核紀錄</h3>
          <ul className={styles.timeline}>
            {c.reviews.map((r, i) => (
              <li key={i}>
                <span className={styles.when}>{formatDateTime(r.created_at)}</span>
                {r.reviewer} {r.decision === "approved" ? "通過" : "排除"}
                {r.reject_reason && `：${REJECT_REASON_LABELS[r.reject_reason]}`}
                {r.note && ` — ${r.note}`}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* 區塊：往來紀錄 */}
      <section className={styles.block}>
        <h3 className={styles.blockTitle}>往來紀錄</h3>
        <ul className={styles.timeline}>
          {c.activities.map((a, i) => (
            <li key={i}>
              <span className={styles.when}>{formatDateTime(a.created_at)}</span>
              {a.user ?? "系統"} · {ACTIVITY_LABELS[a.action] ?? a.action}
              {a.action === "status_change" && a.to_value && (
                <>
                  ：{STATUS_LABELS[a.from_value as keyof typeof STATUS_LABELS] ?? a.from_value} →{" "}
                  {STATUS_LABELS[a.to_value as keyof typeof STATUS_LABELS] ?? a.to_value}
                </>
              )}
              {activityNote(a.action, a.note) && ` — ${activityNote(a.action, a.note)}`}
            </li>
          ))}
        </ul>
      </section>

      <RejectDialog
        open={rejectOpen}
        companyIds={[c.company_id]}
        onClose={() => setRejectOpen(false)}
        onDone={() => setRejectOpen(false)}
      />
    </div>
  );
}
