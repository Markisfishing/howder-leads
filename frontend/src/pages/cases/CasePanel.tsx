import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";

import { useAddCaseUpdate, useCase, useUnsubscribeCase } from "../../api/hooks";
import type { CaseDetail, CaseUpdateInput } from "../../api/types";
import { Button } from "../../components/Button";
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
    case "replied":
      return ["replied", "negotiating", "won", "lost"];
    case "negotiating":
      return ["negotiating", "won", "lost"];
    case "won":
    case "lost":
      return [];
    default:
      return ["replied", "negotiating", "won", "lost", "no_response"];
  }
}

/** 案件詳情：資訊、時間軸、回填表單、客戶要求退訂（M3-11b、M3-04a、F-CASE-2、F-CASE-5） */
export function CasePanel({ caseId }: { caseId: number }) {
  const { data, isLoading, error, refetch } = useCase(caseId);
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorState error={error} onRetry={() => void refetch()} />;
  const closed = !!data.closed_at;

  return (
    <section className={styles.card} aria-labelledby="case-title">
      <div className={c.headRow}>
        <h2 id="case-title" className={styles.cardTitle}>
          {data.case_no} <Link to={`/companies/${data.company_id}`}>{data.company_name}</Link>
        </h2>
        <Tag tone={CASE_STATUS_TONE[data.status]}>{CASE_STATUS_LABELS[data.status]}</Tag>
      </div>
      {data.reminders.length > 0 && (
        <div className={c.tags} role="note">
          {data.reminders.map((r) => (
            <Tag key={r} tone="warning">
              {REMINDER_LABELS[r]}
            </Tag>
          ))}
        </div>
      )}
      <dl className={c.facts}>
        <div>
          <dt>聯絡人</dt>
          <dd>{data.contact_name ?? data.contact_email ?? "—"}</dd>
        </div>
        <div>
          <dt>負責業務</dt>
          <dd>{data.owner_name ?? "—"}</dd>
        </div>
        <div>
          <dt>開案</dt>
          <dd>
            {formatDate(data.opened_at)}（{data.origin === "email" ? "開發信" : "加入追蹤"}）
          </dd>
        </div>
        <div>
          <dt>{closed ? "結案" : "下次追蹤日"}</dt>
          <dd>{closed ? formatDate(data.closed_at) : (data.next_follow_up ?? "—")}</dd>
        </div>
        {data.status === "won" && (
          <div>
            <dt>成交金額</dt>
            <dd>{formatTwd(data.amount_twd)}</dd>
          </div>
        )}
      </dl>

      {/* 區塊：時間軸 */}
      <h3 className={styles.label}>時間軸</h3>
      <ol className={c.timeline} aria-label="時間軸">
        <li className={c.event}>
          <span className={c.eventHead}>
            <strong>開案</strong>
            <span className={styles.hint}>{formatDateTime(data.opened_at)}</span>
          </span>
        </li>
        {data.timeline.map((u) => (
          <li key={u.update_id} className={c.event}>
            <span className={c.eventHead}>
              <strong>{CASE_RESULT_LABELS[u.result]}</strong>
              <Tag tone="neutral">{CASE_CHANNEL_LABELS[u.channel]}</Tag>
              <span className={styles.hint}>
                {formatDateTime(u.created_at)}
                {u.user_name && ` · ${u.user_name}`}
                {u.contact_name && ` · ${u.contact_name}`}
              </span>
            </span>
            {u.note && <p className={c.eventNote}>{u.note}</p>}
            {(u.next_follow_up || u.amount_twd) && (
              <p className={styles.hint}>
                {u.next_follow_up && `下次追蹤 ${u.next_follow_up}`}
                {u.amount_twd && ` 成交金額 ${formatTwd(u.amount_twd)}`}
              </p>
            )}
          </li>
        ))}
      </ol>

      {closed ? (
        <p className={styles.hint}>這件案件已結案。如果客戶之後再聯絡，請從推薦清單重新開發。</p>
      ) : (
        <>
          <UpdateForm data={data} />
          <UnsubscribeAction data={data} />
        </>
      )}
    </section>
  );
}

function UpdateForm({ data }: { data: CaseDetail }) {
  const mutation = useAddCaseUpdate();
  const results = allowedResults(data.status);
  const [channel, setChannel] = useState<Channel>("phone");
  const [result, setResult] = useState<Result>(results[0] ?? "replied");
  const [contactId, setContactId] = useState<number | null>(data.contact_id);
  const [note, setNote] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [amount, setAmount] = useState("");
  const [saved, setSaved] = useState("");
  const closing = result === "won" || result === "lost";

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSaved("");
    mutation.mutate(
      {
        id: data.case_id,
        body: {
          channel,
          result,
          contact_id: contactId,
          note: note.trim() || null,
          next_follow_up: closing ? null : followUp || null,
          amount_twd: result === "won" && amount ? Number(amount) : null,
        },
      },
      {
        onSuccess: (res) => {
          setNote("");
          setFollowUp("");
          setAmount("");
          setResult(allowedResults(res.status)[0] ?? "replied");
          setSaved(`已回填：${CASE_RESULT_LABELS[result]}`);
        },
      },
    );
  };

  return (
    <form className={c.form} onSubmit={submit} aria-labelledby="case-update-title">
      <h3 id="case-update-title" className={styles.cardTitle}>
        回填客戶回覆
      </h3>
      <div className={c.formRow}>
        <label className={styles.field}>
          <span className={styles.label}>管道</span>
          <select className={styles.input} value={channel} onChange={(e) => setChannel(e.target.value as Channel)}>
            {CHANNELS.map((ch) => (
              <option key={ch} value={ch}>
                {CASE_CHANNEL_LABELS[ch]}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.field}>
          <span className={styles.label}>結果</span>
          <select className={styles.input} value={result} onChange={(e) => setResult(e.target.value as Result)}>
            {results.map((r) => (
              <option key={r} value={r}>
                {CASE_RESULT_LABELS[r]}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.field}>
          <span className={styles.label}>聯絡人</span>
          <select
            className={styles.input}
            value={contactId ?? ""}
            onChange={(e) => setContactId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">（未指定）</option>
            {data.contacts.map((ct) => (
              <option key={ct.contact_id} value={ct.contact_id}>
                {ct.name ?? ct.email}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className={styles.field}>
        <span className={styles.label}>備註（客戶說了什麼、下一步）</span>
        <textarea
          className={`${styles.input} ${c.note}`}
          rows={4}
          maxLength={2000}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </label>
      <div className={c.formRow}>
        {!closing && (
          <label className={styles.field}>
            <span className={styles.label}>下次追蹤日（選填）</span>
            <input
              type="date"
              className={styles.input}
              min={taipeiToday()}
              value={followUp}
              onChange={(e) => setFollowUp(e.target.value)}
            />
          </label>
        )}
        {result === "won" && (
          <label className={styles.field}>
            <span className={styles.label}>成交金額（新台幣，選填）</span>
            <input
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              className={styles.input}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </label>
        )}
      </div>
      <div className={styles.actions}>
        <Button type="submit" variant="primary" busy={mutation.isPending}>
          儲存回填
        </Button>
      </div>
      <div aria-live="polite">{saved && <p className={styles.hint}>{saved}</p>}</div>
      <InlineError error={mutation.error} />
    </form>
  );
}

function UnsubscribeAction({ data }: { data: CaseDetail }) {
  const mutation = useUnsubscribeCase();
  const [confirming, setConfirming] = useState(false);
  if (!data.contact_id) return null;
  return confirming ? (
    <div className={c.danger} role="alert">
      <p>
        標記後，{data.contact_name ?? data.contact_email} 會改成已退訂，{data.company_name}{" "}
        改成「不再聯絡」，這件案件結案為失敗。之後任何批次都不能再寄信給這家公司。
      </p>
      <div className={styles.actions}>
        <Button
          variant="danger"
          busy={mutation.isPending}
          onClick={() => mutation.mutate({ id: data.case_id }, { onSuccess: () => setConfirming(false) })}
        >
          確定標記退訂
        </Button>
        <Button onClick={() => setConfirming(false)}>取消</Button>
      </div>
      <InlineError error={mutation.error} />
    </div>
  ) : (
    <div className={styles.actions}>
      <Button size="sm" onClick={() => setConfirming(true)}>
        客戶要求退訂…
      </Button>
    </div>
  );
}
