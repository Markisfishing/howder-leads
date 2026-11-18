import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import {
  isBusy,
  useApproveAll,
  useApproveDraft,
  useCampaign,
  useDiscardDraft,
  useDrafts,
  useExclusionReasons,
  useMailConnection,
  usePatchDraft,
  useRegenerateDraft,
  useSendCampaign,
  useUnapproveDraft,
} from "../../api/hooks";
import type { Campaign, Draft, DraftStatus, ExcludedCompany, SendResult } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { Button } from "../../components/Button";
import { Modal } from "../../components/Modal";
import { Empty, ErrorState, InlineError, Loading } from "../../components/StateView";
import { Tag } from "../../components/Tag";
import {
  CAMPAIGN_STATUS_LABELS,
  CAMPAIGN_STATUS_TONE,
  DRAFT_STATUS_LABELS,
  DRAFT_STATUS_TONE,
  displayTemplateName,
  draftErrorText,
  formatDateTime,
} from "../../lib/labels";
import { useDebounced } from "../../lib/useDebounced";
import styles from "../Page.module.css";
import c from "./Campaigns.module.css";
import { MailConnectionBanner } from "./MailConnectionBanner";

const NEEDS_REVIEW = new Set(["pending_review", "failed"]);

/** 已核准而且排好寄送時間的，顯示「已排程」 */
const draftLabel = (d: Draft) => (d.status === "approved" && d.scheduled_at ? "已排程" : DRAFT_STATUS_LABELS[d.status]);

/** 下一封要看的草稿：從目前這封往後找待審核／失敗的，找不到就從頭找 */
export function nextToReview(drafts: Draft[], currentId: number | null): number | null {
  const start = drafts.findIndex((d) => d.draft_id === currentId);
  const order = [...drafts.slice(start + 1), ...drafts.slice(0, Math.max(start, 0))];
  return order.find((d) => NEEDS_REVIEW.has(d.status) && d.draft_id !== currentId)?.draft_id ?? null;
}

/** 預覽佇列（SPEC 6.2 /campaigns/:id · M2-05b、M2-05c、M2-07d、M2-07e） */
export function CampaignReviewPage() {
  const id = Number(useParams().id);
  const location = useLocation();
  const excluded = (location.state as { excluded?: ExcludedCompany[] } | null)?.excluded ?? [];
  const campaign = useCampaign(id);
  const { data: reasonLabels = {} } = useExclusionReasons();
  const [currentId, setCurrentId] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const [focusEditor, setFocusEditor] = useState(false);
  const [draftSearch, setDraftSearch] = useState("");
  const [draftStatus, setDraftStatus] = useState<DraftStatus | "all">("pending_review");
  const [draftPage, setDraftPage] = useState(1);
  const [editorOpen, setEditorOpen] = useState(false);

  const debouncedDraftSearch = useDebounced(draftSearch);
  const draftQuery = { q: debouncedDraftSearch.trim() || undefined, status: draftStatus, page: draftPage, page_size: 25 };
  const drafts = useDrafts(id, isBusy(campaign.data), draftQuery);
  const visible = drafts.data?.items ?? [];
  const current = visible.find((d) => d.draft_id === currentId) ?? visible[0] ?? null;

  if (campaign.isLoading) return <Loading />;
  if (campaign.error) return <ErrorState error={campaign.error} onRetry={() => void campaign.refetch()} />;
  if (!campaign.data) return <Empty title="找不到這個邀請信批次" />;
  const cp = campaign.data;

  return (
    <>
      <header className={styles.head}>
        <Link to="/campaigns" className={styles.back}>
          ← 回邀請信列表
        </Link>
        <div className={c.headRow}>
          <h1 className={styles.title}>{cp.name}</h1>
          <span className={c.tags}>
            <Tag tone={CAMPAIGN_STATUS_TONE[cp.status]}>{CAMPAIGN_STATUS_LABELS[cp.status]}</Tag>
          </span>
        </div>
        <section className={c.campaignSummary} aria-label="批次摘要">
          <div><span>已完成</span><strong>{cp.progress.sent + cp.progress.discarded} / {cp.progress.total}</strong></div>
          <div><span>寄件人</span><strong>{cp.owner_name ?? "未指定"}</strong></div>
          <div><span>開始寄送</span><strong>{cp.scheduled_at ? formatDateTime(cp.scheduled_at) : "尚未排程"}</strong></div>
          <div><span>模板</span><strong>{cp.template_name ? `${displayTemplateName(cp.template_name)} v${cp.template_version ?? ""}` : "未指定"}</strong></div>
        </section>
      </header>
      <MailConnectionBanner />
      {excluded.length > 0 && (
        <div className={`${c.banner} ${c.bannerWarn}`} role="note">
          <p>有 {excluded.length} 家沒有產生草稿：</p>
          <ul className={c.blockedList}>
            {excluded.map((e) => (
              <li key={e.company_id}>
                {e.name}：{e.reasons.map((r) => reasonLabels[r] ?? r).join("、")}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div aria-live="polite">{notice && <p className={styles.hint}>{notice}</p>}</div>

      <div className={c.reviewWorkArea}>
        <BatchActions campaign={cp} onNotice={setNotice} />

        {drafts.isLoading ? (
          <Loading />
        ) : drafts.error ? (
          <ErrorState error={drafts.error} onRetry={() => void drafts.refetch()} />
        ) : visible.length === 0 ? (
          <Empty title="這個批次沒有草稿">草稿都已丟棄。可以回列表建立新的批次。</Empty>
        ) : (
          <section className={`${styles.card} ${c.draftQueue}`} aria-labelledby="draft-list-title">
            <div className={c.listHeader}>
              <div><h2 id="draft-list-title" className={styles.cardTitle}>草稿 {drafts.data?.total ?? 0}</h2><p className={styles.meta}>一次顯示 25 封，點選列查看完整信件。</p></div>
              <span className={c.pageSummary}>{drafts.data?.total ? `${(drafts.data.page - 1) * drafts.data.page_size + 1}–${Math.min(drafts.data.page * drafts.data.page_size, drafts.data.total)} / ${drafts.data.total}` : "0 封"}</span>
            </div>
            <div className={c.draftToolbar}>
              <label className={c.searchField}><span className="visually-hidden">搜尋公司或收件人</span><span aria-hidden="true">⌕</span><input type="search" value={draftSearch} onChange={(event) => { setDraftSearch(event.target.value); setDraftPage(1); }} placeholder="搜尋公司或收件人" /></label>
              <nav className={c.statusTabs} aria-label="草稿狀態">
                {(["pending_review", "approved", "sent", "failed", "all"] as const).map((value) => <button key={value} type="button" aria-pressed={draftStatus === value} onClick={() => { setDraftStatus(value); setDraftPage(1); }}>{DRAFT_STATUS_FILTER_LABELS[value]} <strong>{value === "all" ? Object.values(drafts.data?.status_counts ?? {}).reduce((sum, count) => sum + (count ?? 0), 0) : drafts.data?.status_counts[value] ?? 0}</strong></button>)}
              </nav>
            </div>
            {visible.length === 0 ? <Empty title="找不到符合條件的草稿">請換一個公司名稱、收件人或狀態。</Empty> : <div className={c.draftTable} role="table" aria-label="草稿列表">
              <div className={c.draftTableHeader} role="row"><span role="columnheader">公司</span><span role="columnheader">收件人</span><span role="columnheader">狀態</span><span role="columnheader">更新時間</span></div>
              <div role="rowgroup">{visible.map((draft) => <button key={draft.draft_id} type="button" className={c.draftRow} role="row" onClick={() => { setFocusEditor(false); setCurrentId(draft.draft_id); setEditorOpen(true); }}><span><strong>{draft.company_name}</strong></span><span>{draft.contact_name ?? draft.contact_email}</span><span><Tag tone={DRAFT_STATUS_TONE[draft.status]}>{draftLabel(draft)}</Tag></span><time>{draft.approved_at || draft.scheduled_at ? formatDateTime(draft.approved_at ?? draft.scheduled_at ?? "") : "—"}</time></button>)}</div>
            </div>}
            <Pagination page={drafts.data?.page ?? draftPage} pageCount={Math.max(1, Math.ceil((drafts.data?.total ?? 0) / (drafts.data?.page_size ?? 25)))} onPage={setDraftPage} />
          </section>
        )}
      </div>
      {current && <Modal open={editorOpen} onOpenChange={setEditorOpen} variant="side" title={`${current.company_name} · ${draftLabel(current)}`} description={`收件人：${current.contact_name ?? current.contact_email}`}>
        <DraftEditor
          key={current.draft_id}
          draft={current}
          reasonLabels={reasonLabels}
          focusOnMount={focusEditor}
          onNext={() => {
            setFocusEditor(true);
            const next = nextToReview(visible, current.draft_id);
            if (next) setCurrentId(next);
            else setEditorOpen(false);
          }}
          onNotice={setNotice}
        />
      </Modal>}
    </>
  );
}

const DRAFT_STATUS_FILTER_LABELS: Record<DraftStatus | "all", string> = {
  pending_review: "待確認",
  approved: "已核准",
  sent: "已寄出",
  failed: "失敗",
  generating: "產生中",
  discarded: "已丟棄",
  all: "全部",
};

function Pagination({ page, pageCount, onPage }: { page: number; pageCount: number; onPage: (page: number) => void }) {
  return <nav className={c.pagination} aria-label="草稿分頁"><Button size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>上一頁</Button><span>第 {page} / {pageCount} 頁</span><Button size="sm" disabled={page >= pageCount} onClick={() => onPage(page + 1)}>下一頁</Button></nav>;
}

/** 批次層級的動作：全部核准（要再按一次確認）、寄出（只有負責業務；可排程） */
function BatchActions({ campaign, onNotice }: { campaign: Campaign; onNotice: (msg: string) => void }) {
  const { user } = useAuth();
  const approveAll = useApproveAll();
  const send = useSendCampaign();
  const mail = useMailConnection();
  const [confirmAll, setConfirmAll] = useState(false);
  const [sendOpen, setSendOpen] = useState(false);
  const [when, setWhen] = useState("");
  const [result, setResult] = useState<SendResult | null>(null);

  const p = campaign.progress;
  const isOwner = user?.user_id === campaign.owner_id;
  const mailReady = mail.data ? mail.data.status === "not_required" || mail.data.status === "connected" : false;

  return (
    <section className={styles.card} aria-label="批次動作">
      <div className={styles.actions}>
        {p.pending_review > 0 &&
          (confirmAll ? (
            <>
              <Button
                variant="primary"
                busy={approveAll.isPending}
                onClick={() =>
                  approveAll.mutate(campaign.campaign_id, {
                    onSuccess: () => {
                      setConfirmAll(false);
                      onNotice(`已核准 ${p.pending_review} 封草稿`);
                    },
                  })
                }
              >
                確定全部核准 {p.pending_review} 封
              </Button>
              <Button onClick={() => setConfirmAll(false)}>取消</Button>
            </>
          ) : (
            <Button onClick={() => setConfirmAll(true)}>全部核准…</Button>
          ))}
        {isOwner && p.approved > 0 && (
          <Button variant="primary" disabled={!mailReady} onClick={() => setSendOpen(true)}>
            寄出已核准的 {p.approved} 封…
          </Button>
        )}
      </div>
      {confirmAll && (
        <p className={styles.hint} role="alert">
          全部核准表示您已經看過每一封。請再按一次「確定全部核准」。
        </p>
      )}
      {!isOwner && <p className={styles.hint}>信會從負責業務本人的信箱寄出，只有 {campaign.owner_name} 可以寄。</p>}
      {result && result.blocked.length > 0 && (
        <div className={c.error} role="alert">
          <p>有 {result.blocked.length} 封寄出前檢查沒過，已標成失敗：</p>
          <ul className={c.blockedList}>
            {result.blocked.map((b) => (
              <li key={b.draft_id}>{b.company_name}</li>
            ))}
          </ul>
        </div>
      )}
      <InlineError error={approveAll.error} />

      <Modal
        open={sendOpen}
        onOpenChange={setSendOpen}
        title={`寄出 ${p.approved} 封邀請信`}
        description="寄出前系統會再檢查一次退訂與鎖定。每天最多寄 50 封，超過的會排到隔天。"
        footer={
          <>
            <Button onClick={() => setSendOpen(false)}>取消</Button>
            <Button
              variant="primary"
              busy={send.isPending}
              onClick={() =>
                send.mutate(
                  { id: campaign.campaign_id, scheduledAt: when ? new Date(when).toISOString() : undefined },
                  {
                    onSuccess: (res) => {
                      setSendOpen(false);
                      setResult(res);
                      onNotice(`已排入寄送 ${res.scheduled} 封${when ? "（依排程時間寄出）" : "，幾分鐘內會陸續寄出"}`);
                    },
                  },
                )
              }
            >
              {when ? "確定排程寄出" : "確定立即寄出"}
            </Button>
          </>
        }
      >
        <label className={styles.field}>
          <span className={styles.label}>排程時間（不填就立即寄出，台灣時間）</span>
          <input
            type="datetime-local"
            className={styles.input}
            value={when}
            onChange={(e) => setWhen(e.target.value)}
          />
        </label>
        <InlineError error={send.error} />
      </Modal>
    </section>
  );
}

/** 單封草稿：修改、核准（Ctrl+Enter 核准並跳下一封）、取消核准、重新產生、丟棄 */
function DraftEditor({
  draft,
  reasonLabels,
  focusOnMount,
  onNext,
  onNotice,
}: {
  draft: Draft;
  reasonLabels: Record<string, string>;
  focusOnMount: boolean;
  onNext: () => void;
  onNotice: (msg: string) => void;
}) {
  const patch = usePatchDraft();
  const approve = useApproveDraft();
  const unapprove = useUnapproveDraft();
  const discard = useDiscardDraft();
  const regenerate = useRegenerateDraft();
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body_text);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const subjectRef = useRef<HTMLInputElement>(null);

  // 「核准並下一封」換到另一封（key 會重建元件）時，焦點放回主旨，鍵盤可以直接接著審
  useEffect(() => {
    if (focusOnMount) subjectRef.current?.focus();
  }, [focusOnMount]);

  const editable = NEEDS_REVIEW.has(draft.status);
  const dirty = subject !== draft.subject || body !== draft.body_text;
  const busy = patch.isPending || approve.isPending;
  const error = patch.error ?? approve.error ?? unapprove.error ?? discard.error ?? regenerate.error;
  const errText = draftErrorText(draft.last_error, reasonLabels);

  const approveAndNext = async () => {
    if (!editable || busy) return;
    try {
      // 失敗的草稿要先存一次（回到待審核）才能核准
      if (dirty || draft.status === "failed") await patch.mutateAsync({ id: draft.draft_id, body: { subject, body_text: body } });
      await approve.mutateAsync(draft.draft_id);
      onNotice(`已核准「${draft.company_name}」`);
      onNext();
    } catch {
      // 錯誤訊息由 InlineError 顯示
    }
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      void approveAndNext();
    }
  };

  return (
    <section
      className={styles.card}
      aria-labelledby="draft-edit-title"
      onKeyDown={onKeyDown}
    >
      <div className={c.headRow}>
        <h2 id="draft-edit-title" className={styles.cardTitle}>
          {draft.company_name}
        </h2>
        <Tag tone={DRAFT_STATUS_TONE[draft.status]}>{draftLabel(draft)}</Tag>
      </div>
      <p className={styles.hint}>
        收件人：{draft.contact_name ? `${draft.contact_name} · ` : ""}
        {draft.contact_email}
        {draft.scheduled_at && ` · 排程 ${formatDateTime(draft.scheduled_at)}`}
      </p>
      {draft.gen_model && (
        <p className={styles.hint}>
          AI 產生：{draft.gen_model}
          {draft.prompt_version && `（提示詞 ${draft.prompt_version}）`}。AI 只根據公司資料寫稿，請核對內容是否有不實或誇大之處再核准。
        </p>
      )}
      {errText && (
        <p className={c.error} role="alert">
          {errText}
        </p>
      )}

      {draft.status === "generating" ? (
        <Loading label="草稿產生中…" />
      ) : editable ? (
        <>
          <label className={styles.field}>
            <span className={styles.label}>主旨</span>
            <input
              ref={subjectRef}
              className={styles.input}
              value={subject}
              maxLength={200}
              onChange={(e) => setSubject(e.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>內文（退訂說明會自動附在最後）</span>
            <textarea
              className={`${styles.input} ${c.body}`}
              rows={14}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </label>
        </>
      ) : (
        <div>
          <p className={styles.cardTitle}>{draft.subject}</p>
          <div className={c.mailBody}>{draft.body_text}</div>
        </div>
      )}

      <div className={styles.actions}>
        {editable && (
          <>
            <Button variant="primary" busy={busy} onClick={() => void approveAndNext()}>
              核准並下一封
            </Button>
            {dirty && (
              <Button
                busy={patch.isPending}
                onClick={() =>
                  patch.mutate(
                    { id: draft.draft_id, body: { subject, body_text: body } },
                    { onSuccess: () => onNotice("已儲存修改") },
                  )
                }
              >
                只儲存修改
              </Button>
            )}
            <Button
              busy={regenerate.isPending}
              onClick={() => regenerate.mutate(draft.draft_id, { onSuccess: () => onNotice("已重新排入產生") })}
            >
              重新產生
            </Button>
          </>
        )}
        {draft.status === "approved" && (
          <Button busy={unapprove.isPending} onClick={() => unapprove.mutate(draft.draft_id)}>
            {draft.scheduled_at ? "取消核准（不寄這封）" : "取消核准"}
          </Button>
        )}
        {(editable || draft.status === "approved") &&
          (confirmDiscard ? (
            <>
              <Button
                variant="danger"
                busy={discard.isPending}
                onClick={() =>
                  discard.mutate(draft.draft_id, {
                    onSuccess: () => {
                      onNotice(`已丟棄「${draft.company_name}」的草稿`);
                      onNext();
                    },
                  })
                }
              >
                確定丟棄
              </Button>
              <Button onClick={() => setConfirmDiscard(false)}>取消</Button>
            </>
          ) : (
            <Button onClick={() => setConfirmDiscard(true)}>丟棄…</Button>
          ))}
      </div>
      {editable && (
        <p className={styles.hint}>
          鍵盤：在主旨或內文按 <kbd className={c.kbd}>Ctrl</kbd>＋<kbd className={c.kbd}>Enter</kbd> 核准並跳到下一封。
        </p>
      )}
      <InlineError error={error} />
    </section>
  );
}
