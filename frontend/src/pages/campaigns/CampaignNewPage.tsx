import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { NO_CANDIDATE_FILTERS } from "../../api/endpoints";
import { useCandidates, useCreateCampaign, useDimensions, useExclusionReasons, useTemplates } from "../../api/hooks";
import type { Candidate, GenMode } from "../../api/types";
import { Button } from "../../components/Button";
import { Stars } from "../../components/Stars";
import { Empty, ErrorState, InlineError, Loading } from "../../components/StateView";
import { Tag } from "../../components/Tag";
import { displayTemplateName, GEN_MODE_LABELS } from "../../lib/labels";
import { STAR_OPTIONS } from "../recommendations/FilterBar";
import styles from "../Page.module.css";
import c from "./Campaigns.module.css";

const MAX_TARGETS = 200;
const GEN_MODES: GenMode[] = ["template_only", "template_ai", "full_ai"];
const AI_PARAGRAPH = "{{ai_paragraph}}";

function today(): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Taipei" }).format(new Date());
}

/** 建立邀請信批次（SPEC 6.2 /campaigns/new · M2-03d、F-MAIL-1、F-MAIL-7） */
export function CampaignNewPage() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState(NO_CANDIDATE_FILTERS);
  const [search, setSearch] = useState("");
  // 打字停 300ms 才查詢，避免每打一個字就查一次
  useEffect(() => {
    const t = setTimeout(() => setFilters((f) => (f.q === search ? f : { ...f, q: search })), 300);
    return () => clearTimeout(t);
  }, [search]);
  const isFiltered = filters.q.trim() !== "" || filters.industryId !== null || filters.stars !== null;
  const candidates = useCandidates(filters);
  const { data: dims } = useDimensions();
  const templates = useTemplates();
  const { data: reasonLabels = {} } = useExclusionReasons();
  const create = useCreateCampaign();

  const [name, setName] = useState(`${today()} 邀請信`);
  const [templateId, setTemplateId] = useState<number | null>(null);
  const [genMode, setGenMode] = useState<GenMode>("template_only");
  // 勾選的公司 → 選定的聯絡人
  const [selected, setSelected] = useState<Map<number, number | null>>(new Map());

  const eligible = useMemo(() => (candidates.data ?? []).filter((x) => x.reasons.length === 0), [candidates.data]);
  const blocked = useMemo(() => (candidates.data ?? []).filter((x) => x.reasons.length > 0), [candidates.data]);
  const tplId = templateId ?? templates.data?.[0]?.template_id ?? null;
  const currentTemplate = templates.data?.find((t) => t.template_id === tplId);
  // 「模板＋AI 段落」要求模板內文有 {{ai_paragraph}}，不然 AI 寫的段落不會出現在信裡（後端也會擋）
  const templateLacksAiParagraph = genMode === "template_ai" && !!currentTemplate && !currentTemplate.body_text.includes(AI_PARAGRAPH);

  const toggle = (cand: Candidate) => {
    const next = new Map(selected);
    if (next.has(cand.company_id)) next.delete(cand.company_id);
    else next.set(cand.company_id, cand.default_contact_id);
    setSelected(next);
  };
  const allChecked = eligible.length > 0 && eligible.every((x) => selected.has(x.company_id));
  // 全選／全部取消只動目前顯示（篩選後）的公司，其他篩選條件下已勾的不受影響
  const toggleAll = () => {
    const next = new Map(selected);
    if (allChecked) eligible.forEach((x) => next.delete(x.company_id));
    else eligible.forEach((x) => next.has(x.company_id) || next.size >= MAX_TARGETS || next.set(x.company_id, x.default_contact_id));
    setSelected(next);
  };

  const submit = () => {
    if (tplId == null) return;
    create.mutate(
      {
        name: name.trim(),
        template_id: tplId,
        gen_mode: genMode,
        targets: [...selected].map(([company_id, contact_id]) => ({ company_id, contact_id })),
      },
      {
        onSuccess: (res) =>
          navigate(`/campaigns/${res.campaign.campaign_id}`, { state: { excluded: res.excluded } }),
      },
    );
  };

  const reasonText = (codes: string[]) => codes.map((r) => reasonLabels[r] ?? r).join("、");
  const recentSendReason = reasonLabels.RECENTLY_SENT ?? "近期寄過";

  return (
    <>
      <header className={styles.head}>
        <Link to="/campaigns" className={styles.back}>
          ← 回邀請信列表
        </Link>
        <h1 className={styles.title}>建立邀請信批次</h1>
        <p className={styles.meta}>
          勾選要寄的公司。已退訂、不再聯絡、由其他業務負責、或{recentSendReason}的公司會自動排除並說明原因。
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
                  {displayTemplateName(t.name)}（第 {t.version} 版）
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
            {GEN_MODES.map((m) => (
              <label key={m} className={c.radio}>
                <input type="radio" name="gen_mode" checked={genMode === m} onChange={() => setGenMode(m)} />{" "}
                {GEN_MODE_LABELS[m]}
              </label>
            ))}
          </div>
          {genMode !== "template_only" && (
            <span className={styles.hint}>
              AI 只根據公司資料寫稿，可能有不精確的地方；每封信都要你預覽、核對事實後才能核准，系統不會自動寄出。
            </span>
          )}
          {templateLacksAiParagraph && (
            <span className={c.error} role="alert">
              這份模板的內文沒有 {AI_PARAGRAPH}，AI 寫的段落不會出現在信裡。請換一份模板，或請管理員在模板加上 {AI_PARAGRAPH}。
            </span>
          )}
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
              {allChecked ? "全部取消" : `全選（${eligible.length} 家）`}
            </Button>
          )}
        </div>
        <div className={c.filterRow} role="search" aria-label="篩選候選公司">
          <label className={`${styles.field} ${c.filterSearch}`}>
            <span className={styles.label}>搜尋</span>
            <input
              className={styles.input}
              type="search"
              placeholder="公司名稱或統編"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>產業</span>
            <select
              className={styles.input}
              value={filters.industryId ?? ""}
              onChange={(e) => setFilters({ ...filters, industryId: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">全部產業</option>
              {dims?.industries.map((i) => (
                <option key={i.industry_id} value={i.industry_id}>
                  {i.name}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.field}>
            <span className={styles.label}>星級</span>
            <select
              className={styles.input}
              value={filters.stars ?? ""}
              onChange={(e) => setFilters({ ...filters, stars: e.target.value === "" ? null : Number(e.target.value) })}
            >
              <option value="">全部</option>
              {STAR_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          {isFiltered && (
            <Button
              size="sm"
              onClick={() => {
                setSearch("");
                setFilters(NO_CANDIDATE_FILTERS);
              }}
            >
              清除篩選
            </Button>
          )}
        </div>
        {candidates.isLoading ? (
          <Loading />
        ) : candidates.error ? (
          <ErrorState error={candidates.error} onRetry={() => void candidates.refetch()} />
        ) : eligible.length === 0 && blocked.length === 0 ? (
          isFiltered ? (
            <Empty title="沒有符合條件的公司">換個關鍵字或清除篩選再試試。已選的公司不受影響。</Empty>
          ) : (
            <Empty title="目前沒有可以寄的公司">先到推薦清單審核通過，並認領公司、新增聯絡人。</Empty>
          )
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
          disabled={
            selected.size === 0 || selected.size > MAX_TARGETS || !name.trim() || tplId == null || templateLacksAiParagraph
          }
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
