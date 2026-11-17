import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useCandidates, useCreateCampaign, useExclusionReasons, useTemplates } from "../../api/hooks";
import type { Candidate, GenMode } from "../../api/types";
import { Button } from "../../components/Button";
import { Stars } from "../../components/Stars";
import { Empty, ErrorState, InlineError, Loading } from "../../components/StateView";
import { Tag } from "../../components/Tag";
import { GEN_MODE_LABELS } from "../../lib/labels";
import styles from "../Page.module.css";
import c from "./Campaigns.module.css";

const MAX_TARGETS = 200;
const AI_MODES: GenMode[] = ["template_ai", "full_ai"]; // M4 開放

function today(): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Taipei" }).format(new Date());
}

/** 建立邀請信批次（SPEC 6.2 /campaigns/new · M2-03d、F-MAIL-1、F-MAIL-7） */
export function CampaignNewPage() {
  const navigate = useNavigate();
  const candidates = useCandidates();
  const templates = useTemplates();
  const { data: reasonLabels = {} } = useExclusionReasons();
  const create = useCreateCampaign();

  const [name, setName] = useState(`${today()} 邀請信`);
  const [templateId, setTemplateId] = useState<number | null>(null);
  // 勾選的公司 → 選定的聯絡人
  const [selected, setSelected] = useState<Map<number, number | null>>(new Map());

  const eligible = useMemo(() => (candidates.data ?? []).filter((x) => x.reasons.length === 0), [candidates.data]);
  const blocked = useMemo(() => (candidates.data ?? []).filter((x) => x.reasons.length > 0), [candidates.data]);
  const tplId = templateId ?? templates.data?.[0]?.template_id ?? null;

  const toggle = (cand: Candidate) => {
    const next = new Map(selected);
    if (next.has(cand.company_id)) next.delete(cand.company_id);
    else next.set(cand.company_id, cand.default_contact_id);
    setSelected(next);
  };
  const allChecked = eligible.length > 0 && eligible.every((x) => selected.has(x.company_id));
  const toggleAll = () =>
    setSelected(
      allChecked ? new Map() : new Map(eligible.slice(0, MAX_TARGETS).map((x) => [x.company_id, x.default_contact_id])),
    );

  const submit = () => {
    if (tplId == null) return;
    create.mutate(
      {
        name: name.trim(),
        template_id: tplId,
        gen_mode: "template_only",
        targets: [...selected].map(([company_id, contact_id]) => ({ company_id, contact_id })),
      },
      {
        onSuccess: (res) =>
          navigate(`/campaigns/${res.campaign.campaign_id}`, { state: { excluded: res.excluded } }),
      },
    );
  };

  const reasonText = (codes: string[]) => codes.map((r) => reasonLabels[r] ?? r).join("、");

  return (
    <>
      <header className={styles.head}>
        <Link to="/campaigns" className={styles.back}>
          ← 回邀請信列表
        </Link>
        <h1 className={styles.title}>建立邀請信批次</h1>
        <p className={styles.meta}>
          勾選要寄的公司。已退訂、不再聯絡、由其他業務負責、或 14 天內寄過的公司會自動排除並說明原因。
        </p>
      </header>

      {/* 區塊：批次設定 */}
      <section className={styles.card} aria-labelledby="campaign-setting-title">
        <h2 id="campaign-setting-title" className={styles.cardTitle}>
          批次設定
        </h2>
        <label className={styles.field}>
          <span className={styles.label}>批次名稱</span>
          <input className={styles.input} value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>郵件模板</span>
          {templates.isLoading ? (
            <Loading />
          ) : templates.data && templates.data.length > 0 ? (
            <select
              className={styles.input}
              value={tplId ?? ""}
              onChange={(e) => setTemplateId(Number(e.target.value))}
            >
              {templates.data.map((t) => (
                <option key={t.template_id} value={t.template_id}>
                  {t.name}（第 {t.version} 版）
                </option>
              ))}
            </select>
          ) : (
            <span className={styles.hint}>還沒有可用的模板，請管理員先在「郵件模板」建立。</span>
          )}
        </label>
        <fieldset className={styles.field}>
          <legend className={styles.label}>生成方式</legend>
          <div className={c.radioRow}>
            <label className={c.radio}>
              <input type="radio" name="gen_mode" checked readOnly /> {GEN_MODE_LABELS.template_only}
            </label>
            {AI_MODES.map((m) => (
              <label key={m} className={c.radio}>
                <input type="radio" name="gen_mode" disabled /> {GEN_MODE_LABELS[m]}（M4 開放）
              </label>
            ))}
          </div>
        </fieldset>
      </section>

      {/* 區塊：選擇對象 */}
      <section className={styles.card} aria-labelledby="campaign-targets-title">
        <div className={c.headRow}>
          <h2 id="campaign-targets-title" className={styles.cardTitle}>
            選擇對象
          </h2>
          {eligible.length > 0 && (
            <Button size="sm" onClick={toggleAll}>
              {allChecked ? "全部取消" : `全選（${Math.min(eligible.length, MAX_TARGETS)} 家）`}
            </Button>
          )}
        </div>
        {candidates.isLoading ? (
          <Loading />
        ) : candidates.error ? (
          <ErrorState error={candidates.error} onRetry={() => void candidates.refetch()} />
        ) : eligible.length === 0 && blocked.length === 0 ? (
          <Empty title="目前沒有可以寄的公司">先到推薦清單審核通過，並認領公司、新增聯絡人。</Empty>
        ) : (
          <ul className={c.candidates}>
            {eligible.map((cand) => {
              const checked = selected.has(cand.company_id);
              const contacts = cand.contacts.filter((x) => !x.unsubscribed);
              return (
                <li key={cand.company_id} className={c.candidate}>
                  <input
                    id={`cand-${cand.company_id}`}
                    type="checkbox"
                    className={c.check}
                    checked={checked}
                    onChange={() => toggle(cand)}
                  />
                  <label htmlFor={`cand-${cand.company_id}`} className={c.candidateInfo}>
                    <span className={c.candidateName}>
                      {cand.name}
                      {cand.stars != null && <Stars stars={cand.stars} priority={cand.priority} />}
                    </span>
                    <span className={styles.hint}>{cand.industry ?? "產業未分類"}</span>
                  </label>
                  {checked && contacts.length > 1 && (
                    <label className={`${styles.field} ${c.contactSelect}`}>
                      <span className={styles.label}>寄給</span>
                      <select
                        className={styles.input}
                        value={selected.get(cand.company_id) ?? ""}
                        onChange={(e) => setSelected(new Map(selected).set(cand.company_id, Number(e.target.value)))}
                      >
                        {contacts.map((ct) => (
                          <option key={ct.contact_id} value={ct.contact_id}>
                            {ct.name ?? "（未填姓名）"} · {ct.email}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  {checked && contacts.length === 1 && (
                    <span className={`${styles.hint} ${c.contactSelect}`}>
                      寄給 {contacts[0]?.name ?? ""} {contacts[0]?.email}
                    </span>
                  )}
                </li>
              );
            })}
            {blocked.map((cand) => (
              <li key={cand.company_id} className={`${c.candidate} ${c.candidateOff}`}>
                <input type="checkbox" className={c.check} disabled aria-label={`${cand.name}（不能選）`} />
                <span className={c.candidateInfo}>
                  <span className={c.candidateName}>
                    {cand.name} <Tag tone="neutral">已排除</Tag>
                  </span>
                  <span className={styles.hint}>原因：{reasonText(cand.reasons)}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* 區塊：送出列（固定在底部） */}
      <div className={c.stickyBar}>
        <span aria-live="polite">
          已選 {selected.size} 家{selected.size > MAX_TARGETS && `（最多 ${MAX_TARGETS} 家）`}
        </span>
        <Button
          variant="primary"
          disabled={selected.size === 0 || selected.size > MAX_TARGETS || !name.trim() || tplId == null}
          busy={create.isPending}
          onClick={submit}
        >
          產生 {selected.size} 封草稿
        </Button>
      </div>
      <InlineError error={create.error} />
    </>
  );
}
