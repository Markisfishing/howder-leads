import { useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { useAddCaseUpdate, useCase, useUnsubscribeCase } from "../../api/hooks";
import type { CaseDetail, CaseTimelineItem, CaseUpdateInput } from "../../api/types";
import { Button } from "../../components/Button";
import { Modal } from "../../components/Modal";
import { ErrorState, InlineError, Loading } from "../../components/StateView";
import { Tag } from "../../components/Tag";
import {
  CASE_CHANNEL_LABELS,
  CASE_RESULT_LABELS,
  CASE_STATUS_LABELS,
  CASE_STATUS_TONE,
  formatDate,
  formatDateTime,
  formatTwd,
  REMINDER_LABELS,
  taipeiToday,
} from "../../lib/labels";
import styles from "../Page.module.css";
import c from "./Cases.module.css";

type Channel = CaseUpdateInput["channel"];
type Result = CaseUpdateInput["result"];
const CHANNELS: Channel[] = ["email", "line", "wechat", "phone", "visit", "other"];

/** 依案件目前狀態，能回填哪些結果（和後端 domain/case_rules 一致；不能往回走） */
export function allowedResults(status: CaseDetail["status"]): Result[] {
  switch (status) {
    case "replied": return ["replied", "negotiating", "won", "lost"];
    case "negotiating": return ["negotiating", "won", "lost"];
    case "won":
    case "lost": return [];
    default: return ["replied", "negotiating", "won", "lost", "no_response"];
  }
}

export function CaseDetailPage() {
  const id = Number(useParams().id) || null;
  const [sp] = useSearchParams();
  const backSearch = sp.toString() ? `?${sp.toString()}` : "";
  if (!id) return <ErrorState error={new Error("找不到案件編號")} />;
  return <main className={c.detailPage}><Link className={styles.back} to={`/cases${backSearch}`}>← 返回案件</Link><CasePanel caseId={id} /></main>;
}

/** 獨立案件詳情頁：頁首先回答狀態、最後事件與下一步，再顯示紀錄和資訊。 */
export function CasePanel({ caseId }: { caseId: number }) {
  const { data, isLoading, error, refetch } = useCase(caseId);
  const [updateOpen, setUpdateOpen] = useState(false);
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorState error={error} onRetry={() => void refetch()} />;
  const closed = !!data.closed_at;
  const latest = [...data.timeline].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const firstReminder = data.reminders[0];
  const nextAction = firstReminder === "overdue_report"
    ? "回填聯絡結果"
    : firstReminder === "follow_up_due"
      ? "今天聯絡客戶"
      : firstReminder === "no_response"
        ? "安排電話或拜訪"
        : data.next_follow_up
          ? `下次追蹤：${formatDate(data.next_follow_up)}`
          : "等待客戶回覆";

  return <>
    <header className={c.detailHeader}>
      <div className={c.detailTitleRow}>
        <div><div className={c.caseEyebrow}>{data.case_no} · {data.owner_name ?? "未指定負責人"}</div><h1 className={styles.title}>{data.company_name}</h1></div>
        <Tag tone={CASE_STATUS_TONE[data.status]}>{CASE_STATUS_LABELS[data.status]}</Tag>
      </div>
      <div className={c.nextAction}>
        <div><span className={c.nextActionLabel}>{data.reminders.length > 0 ? "該追蹤了" : "目前進度"}</span><strong>{nextAction}</strong><span className={styles.hint}>上次聯絡：{latest ? formatDateTime(latest.created_at) : formatDateTime(data.opened_at)}</span></div>
        {!closed && <Button variant="primary" onClick={() => setUpdateOpen(true)}>記錄聯絡結果</Button>}
      </div>
      {data.reminders.length > 0 && <div className={c.tags} role="note">{data.reminders.map((reminder) => <Tag key={reminder} tone="warning">{REMINDER_LABELS[reminder]}</Tag>)}</div>}
    </header>

    <div className={c.detailLayout}>
      <section className={styles.card} aria-labelledby="timeline-title"><div className={c.sectionHeading}><h2 id="timeline-title" className={styles.cardTitle}>往來紀錄</h2><span className={styles.hint}>{data.timeline.length + 1} 筆活動</span></div><ActivityTimeline data={data} /></section>
      <aside className={c.infoCard} aria-labelledby="case-info-title"><h2 id="case-info-title" className={styles.cardTitle}>案件資訊</h2><dl className={c.infoList}><Info label="聯絡人">{data.contact_name ?? data.contact_email ?? "未指定"}</Info><Info label="負責業務">{data.owner_name ?? "未指定"}</Info><Info label="開案日">{formatDate(data.opened_at)}</Info><Info label={closed ? "結案日" : "下一次追蹤"}>{closed ? formatDate(data.closed_at) : data.next_follow_up ? formatDate(data.next_follow_up) : "尚未設定"}</Info>{data.status === "won" && <Info label="成交金額">{formatTwd(data.amount_twd)}</Info>}</dl><div className={c.infoActions}><Link className={c.actionLink} to={`/companies/${data.company_id}`}>查看公司資料</Link>{!closed && <MoreActions data={data} />}</div></aside>
    </div>

    {closed && <p className={styles.hint}>這件案件已結案。如果客戶之後再聯絡，請從推薦清單重新開發。</p>}
    {!closed && <UpdateForm data={data} open={updateOpen} onOpenChange={setUpdateOpen} />}
  </>;
}

function Info({ label, children }: { label: string; children: ReactNode }) { return <div><dt>{label}</dt><dd>{children}</dd></div>; }

function ActivityTimeline({ data }: { data: CaseDetail }) {
  const events = useMemo(() => {
    const opened: CaseTimelineItem = { update_id: -1, user_name: null, channel: "system", contact_name: null, result: "sent", note: data.origin === "email" ? "由開發信建立案件" : "由加入追蹤建立案件", next_follow_up: null, amount_twd: null, created_at: data.opened_at };
    return [opened, ...data.timeline].sort((a, b) => b.created_at.localeCompare(a.created_at) || b.update_id - a.update_id);
  }, [data]);
  return <ol className={c.timeline} aria-label="往來紀錄">{events.map((event, index) => {
    const day = timelineDay(event.created_at);
    const previous = index > 0 ? events[index - 1] : undefined;
    const showDay = !previous || day !== timelineDay(previous.created_at);
    const opening = event.update_id === -1;
    return <li key={`${event.update_id}-${event.created_at}`} className={c.timelineItem}>{showDay && <h3 className={c.timelineDay}>{day}</h3>}<div className={c.event}><span className={c.eventNode} aria-hidden="true">{channelIcon(event.channel)}</span><div className={c.eventContent}><div className={c.eventHead}><strong>{opening ? "建立案件" : CASE_RESULT_LABELS[event.result]}</strong><span className={c.channel}>{channelIcon(event.channel)} {CASE_CHANNEL_LABELS[event.channel]}</span><time className={styles.hint}>{formatDateTime(event.created_at)}</time></div>{!opening && <p className={c.eventMeta}>{event.user_name ?? "系統"}{event.contact_name ? ` 與 ${event.contact_name}` : ""}</p>}{event.note && <p className={c.eventNote}>{event.note}</p>}{(event.next_follow_up || event.amount_twd) && <p className={c.eventFollowUp}>{event.next_follow_up ? `下一次追蹤：${formatDate(event.next_follow_up)}` : ""}{event.amount_twd ? ` · 成交金額 ${formatTwd(event.amount_twd)}` : ""}</p>}</div></div></li>;
  })}</ol>;
}

function timelineDay(iso: string): string {
  const key = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Taipei" }).format(new Date(iso));
  const today = taipeiToday();
  const yesterday = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Taipei" }).format(new Date(Date.now() - 86400000));
  if (key === today) return "今天";
  if (key === yesterday) return "昨天";
  return new Intl.DateTimeFormat("zh-TW", { month: "long", day: "numeric", timeZone: "Asia/Taipei" }).format(new Date(iso));
}

function channelIcon(channel: CaseTimelineItem["channel"]): string {
  return { email: "✉", line: "◈", wechat: "◉", phone: "☎", visit: "⌂", other: "•", system: "⚙" }[channel];
}

function UpdateForm({ data, open, onOpenChange }: { data: CaseDetail; open: boolean; onOpenChange: (open: boolean) => void }) {
  const mutation = useAddCaseUpdate();
  const results = allowedResults(data.status);
  const [channel, setChannel] = useState<Channel>("phone");
  const [result, setResult] = useState<Result>(results[0] ?? "replied");
  const [contactId, setContactId] = useState<number | null>(data.contact_id);
  const [note, setNote] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [amount, setAmount] = useState("");
  const closing = result === "won" || result === "lost";

  const submit = (event: FormEvent) => {
    event.preventDefault();
    mutation.mutate({ id: data.case_id, body: { channel, result, contact_id: contactId, note: note.trim() || null, next_follow_up: closing ? null : followUp || null, amount_twd: result === "won" && amount ? Number(amount) : null } }, { onSuccess: () => { setNote(""); setFollowUp(""); setAmount(""); onOpenChange(false); } });
  };

  return <Modal open={open} onOpenChange={onOpenChange} title="記錄聯絡結果" description="回填後會更新案件狀態與下一步提醒。"><form className={c.form} onSubmit={submit}>
    <div className={c.formRow}><label className={styles.field}><span className={styles.label}>管道</span><select className={styles.input} value={channel} onChange={(event) => setChannel(event.target.value as Channel)}>{CHANNELS.map((item) => <option key={item} value={item}>{CASE_CHANNEL_LABELS[item]}</option>)}</select></label><label className={styles.field}><span className={styles.label}>結果</span><select className={styles.input} value={result} onChange={(event) => setResult(event.target.value as Result)}>{results.map((item) => <option key={item} value={item}>{CASE_RESULT_LABELS[item]}</option>)}</select></label><label className={styles.field}><span className={styles.label}>聯絡人</span><select className={styles.input} value={contactId ?? ""} onChange={(event) => setContactId(event.target.value ? Number(event.target.value) : null)}><option value="">（未指定）</option>{data.contacts.map((contact) => <option key={contact.contact_id} value={contact.contact_id}>{contact.name ?? contact.email}</option>)}</select></label></div>
    <label className={styles.field}><span className={styles.label}>客戶說了什麼？</span><textarea className={`${styles.input} ${c.note}`} rows={4} maxLength={2000} value={note} onChange={(event) => setNote(event.target.value)} /></label>
    <div className={c.formRow}>{!closing && <label className={styles.field}><span className={styles.label}>下一次追蹤</span><input type="date" className={styles.input} min={taipeiToday()} value={followUp} onChange={(event) => setFollowUp(event.target.value)} /></label>}{result === "won" && <label className={styles.field}><span className={styles.label}>成交金額（新台幣，選填）</span><input type="number" inputMode="numeric" min={0} step={1} className={styles.input} value={amount} onChange={(event) => setAmount(event.target.value)} /></label>}</div>
    <div className={c.modalActions}><Button onClick={() => onOpenChange(false)}>取消</Button><Button type="submit" variant="primary" busy={mutation.isPending}>儲存紀錄</Button></div><InlineError error={mutation.error} />
  </form></Modal>;
}

function MoreActions({ data }: { data: CaseDetail }) {
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [wholeCompany, setWholeCompany] = useState(false);
  const mutation = useUnsubscribeCase();
  if (!data.contact_id) return null;
  // 只用來決定說明文字；公司要不要改「不再聯絡」由後端 domain 判斷（F-CASE-5、M3-17）
  const othersLeft = data.contacts.some((x) => x.contact_id !== data.contact_id && !x.unsubscribed);
  const stops = wholeCompany || !othersLeft;
  const who = data.contact_name ?? data.contact_email;
  return <div className={c.moreActions}><Button size="sm" aria-expanded={open} onClick={() => setOpen((value) => !value)}>更多操作 ⋯</Button>{open && <div className={c.actionMenu}><button type="button" onClick={() => { setConfirming(true); setOpen(false); }}>客戶要求停止聯絡</button></div>}{confirming && <div className={c.danger} role="alert"><p>{stops ? `標記後，${who} 會改成已退訂，${data.company_name} 改成「不再聯絡」，這件案件會結案為失敗。` : `標記後，只有 ${who} 改成已退訂；${data.company_name} 還有其他聯絡人，案件照常進行，可以改用其他聯絡人。`}</p>{othersLeft && <label className={c.checkRow}><input type="checkbox" checked={wholeCompany} onChange={(event) => setWholeCompany(event.target.checked)} />客戶表示整家公司都不要再聯絡</label>}<div className={styles.actions}><Button variant="danger" busy={mutation.isPending} onClick={() => mutation.mutate({ id: data.case_id, wholeCompany }, { onSuccess: () => setConfirming(false) })}>確定標記退訂</Button><Button onClick={() => setConfirming(false)}>取消</Button></div><InlineError error={mutation.error} /></div>}</div>;
}
