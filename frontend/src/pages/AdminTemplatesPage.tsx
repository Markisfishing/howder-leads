import { useLayoutEffect, useRef, useState } from "react";

import { useTemplateActions, useTemplatePreview, useTemplateVariables, useTemplateVersions, useTemplates } from "../api/hooks";
import type { EmailTemplate } from "../api/types";
import { Button } from "../components/Button";
import { Empty, ErrorState, InlineError, Loading } from "../components/StateView";
import { Tag } from "../components/Tag";
import { displayTemplateName, formatDateTime } from "../lib/labels";
import { useDebounced } from "../lib/useDebounced";
import styles from "./Page.module.css";
import t from "./Templates.module.css";

const NEW_BODY = "{{contact_name}} 您好：\n\n\n\n{{sender_name}}\n厚達電子 業務部\n\n{{unsubscribe}}";

type Editing = { kind: "new" } | { kind: "edit"; template: EmailTemplate } | null;

/** 郵件模板管理（SPEC 6.2 /admin/templates · M2-02b）：列表、編輯（存檔會新增版本）、用假資料即時預覽 */
export function AdminTemplatesPage() {
  const { data, isLoading, error, refetch } = useTemplates();
  const [editing, setEditing] = useState<Editing>(null);
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");

  return (
    <>
      <header className={styles.head}>
        <h1 className={styles.title}>郵件模板</h1>
        <p className={styles.meta}>修改後會存成新版本，已產生的草稿不受影響。</p>
      </header>
      <div aria-live="polite">{notice && <p className={styles.hint}>{notice}</p>}</div>

      {editing ? (
        <TemplateEditor
          key={editing.kind === "edit" ? editing.template.template_id : "new"}
          template={editing.kind === "edit" ? editing.template : null}
          onDone={(msg) => {
            setEditing(null);
            setNotice(msg);
          }}
          onCancel={() => setEditing(null)}
        />
      ) : (
        <section className={styles.card}>
          <div className={t.listHead}>
            <h2 className={styles.cardTitle}>使用中的模板</h2>
            <Button variant="primary" onClick={() => setEditing({ kind: "new" })}>
              新增模板
            </Button>
          </div>
          <label className={t.searchField}><span className="visually-hidden">搜尋模板名稱</span><span aria-hidden="true">⌕</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜尋模板名稱" /></label>
          {isLoading ? (
            <Loading />
          ) : error ? (
            <ErrorState error={error} onRetry={() => void refetch()} />
          ) : !data || data.length === 0 ? (
            <Empty title="還沒有模板">按「新增模板」建立第一份，或請管理員執行初版模板種子。</Empty>
          ) : (
            <TemplateList templates={data.filter((tpl) => tpl.name.toLowerCase().includes(search.trim().toLowerCase()))} onEdit={(tpl) => setEditing({ kind: "edit", template: tpl })} onNotice={setNotice} />
          )}
        </section>
      )}
    </>
  );
}

function TemplateList({
  templates,
  onEdit,
  onNotice,
}: {
  templates: EmailTemplate[];
  onEdit: (tpl: EmailTemplate) => void;
  onNotice: (msg: string) => void;
}) {
  const { archive } = useTemplateActions();
  const [confirmId, setConfirmId] = useState<number | null>(null);
  return (
    <>
      <ul className={t.list}>
        {templates.map((tpl) => (
          <li key={tpl.template_id} className={t.item}>
            <div className={t.itemInfo}>
              <p className={t.itemName}>
                {displayTemplateName(tpl.name)} <Tag tone="info">第 {tpl.version} 版</Tag>
              </p>
              <p className={styles.hint}>主旨：{tpl.subject}</p>
              <p className={t.itemMeta}><Tag tone="success">使用中</Tag><span>更新於 {formatDateTime(tpl.created_at)}</span><span>使用中的批次 {tpl.usage_count ?? 0}</span></p>
            </div>
            <div className={styles.actions}>
              <Button size="sm" onClick={() => onEdit(tpl)}>
                編輯
              </Button>
              {confirmId === tpl.template_id ? (
                <>
                  <Button
                    size="sm"
                    variant="danger"
                    busy={archive.isPending}
                    onClick={() =>
                      archive.mutate(tpl.template_id, {
                        onSuccess: () => {
                          setConfirmId(null);
                          onNotice(`已停用「${displayTemplateName(tpl.name)}」`);
                        },
                      })
                    }
                  >
                    確定停用
                  </Button>
                  <Button size="sm" onClick={() => setConfirmId(null)}>
                    取消
                  </Button>
                </>
              ) : <details className={t.itemMenu}><summary className={t.menuTrigger} aria-label={`更多操作 ${displayTemplateName(tpl.name)}`}>⋯</summary><div className={t.menuPanel}><button type="button" onClick={() => setConfirmId(tpl.template_id)}>停用</button></div></details>}
            </div>
          </li>
        ))}
      </ul>
      <InlineError error={archive.error} />
    </>
  );
}

function TemplateEditor({
  template,
  onDone,
  onCancel,
}: {
  template: EmailTemplate | null;
  onDone: (msg: string) => void;
  onCancel: () => void;
}) {
  const { create, update } = useTemplateActions();
  const { data: variables } = useTemplateVariables();
  const versions = useTemplateVersions(template?.template_id ?? null);
  const [name, setName] = useState(template ? displayTemplateName(template.name) : "");
  const [subject, setSubject] = useState(template?.subject ?? "");
  const [body, setBody] = useState(template?.body_text ?? NEW_BODY);
  const [previewOpen, setPreviewOpen] = useState(false);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  // 內文依內容自動增高，不出現內部捲軸（捲動交給整個頁面）
  useLayoutEffect(() => {
    const el = bodyRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight + el.offsetHeight - el.clientHeight}px`;
  }, [body]);
  const preview = useTemplatePreview(useDebounced(subject), useDebounced(body));
  const mutation = template ? update : create;

  const insert = (variable: string) => {
    const el = bodyRef.current;
    const token = `{{${variable}}}`;
    const currentBody = el?.value ?? body;
    const start = Math.min(el?.selectionStart ?? currentBody.length, currentBody.length);
    const end = Math.min(el?.selectionEnd ?? currentBody.length, currentBody.length);
    const scrollTop = el?.scrollTop ?? 0;
    setBody((value) => value.slice(0, start) + token + value.slice(end));
    requestAnimationFrame(() => {
      if (!el) return;
      el.focus({ preventScroll: true });
      el.scrollTop = scrollTop;
      el.setSelectionRange(start + token.length, start + token.length);
    });
  };

  const save = () => {
    const payload = { name: name.trim(), subject: subject.trim(), body_text: body };
    if (template) {
      update.mutate(
        { id: template.template_id, body: payload },
        { onSuccess: (tpl) => onDone(`已儲存「${tpl.name}」第 ${tpl.version} 版`) },
      );
    } else {
      create.mutate(payload, { onSuccess: (tpl) => onDone(`已新增「${tpl.name}」`) });
    }
  };

  return (
    <div className={t.editorGrid}>
      <section className={`${styles.card} ${t.editorCard}`} aria-labelledby="tpl-edit-title">
        <div className={t.editorHeader}>
          <h2 id="tpl-edit-title" className={styles.cardTitle}>
            {template ? `編輯「${displayTemplateName(template.name)}」` : "新增模板"}
          </h2>
          <Button
            size="sm"
            className={t.previewToggle}
            aria-expanded={previewOpen}
            aria-controls="tpl-preview-panel"
            onClick={() => setPreviewOpen((open) => !open)}
          >
            {previewOpen ? "隱藏預覽" : "顯示預覽"}
          </Button>
        </div>
        {template && <p className={styles.hint}>存檔會建立第 {template.version + 1} 版，既有草稿不受影響。</p>}
        <label className={styles.field}>
          <span className={styles.label}>模板名稱</span>
          <input className={styles.input} value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>主旨（一行）</span>
          <input className={styles.input} value={subject} maxLength={200} onChange={(e) => setSubject(e.target.value)} />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>內文（純文字；空一行就是新段落）</span>
          <textarea
            ref={bodyRef}
            className={`${styles.input} ${t.body}`}
            rows={5}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
        </label>
        <div className={t.variablePanel}>
          <div className={t.variableHeader}>
            <span className={styles.label}>插入變數</span>
            <span className={styles.hint}>插入到目前游標位置</span>
          </div>
          <div className={t.vars} aria-label="可插入的變數">
            {variables?.map((v) => (
              <button key={v.name} type="button" className={t.var} onClick={() => insert(v.name)} title={`插入 ${v.label}`}>
                {v.label}
              </button>
            ))}
          </div>
        </div>
        <div className={styles.actions}>
          <Button
            variant="primary"
            disabled={!name.trim() || !subject.trim() || !body.trim()}
            busy={mutation.isPending}
            onClick={save}
          >
            {template ? "存成新版本" : "建立模板"}
          </Button>
          <Button onClick={onCancel}>取消</Button>
        </div>
        <InlineError error={mutation.error} />

        {template && versions.data && versions.data.length > 1 && (
          <details className={t.versions}>
            <summary>過去的版本（{versions.data.length - 1}）</summary>
            <ul>
              {versions.data
                .filter((v) => !v.is_active)
                .map((v) => (
                  <li key={v.template_id}>
                    第 {v.version} 版 · {formatDateTime(v.created_at)} · 主旨：{v.subject}
                  </li>
                ))}
            </ul>
          </details>
        )}
      </section>

      {/* 區塊：即時預覽（假資料） */}
      <section id="tpl-preview-panel" className={`${styles.card} ${t.previewCard} ${previewOpen ? t.previewOpen : ""}`} aria-labelledby="tpl-preview-title" aria-live="polite">
        <h2 id="tpl-preview-title" className={styles.cardTitle}>
          預覽（假資料）
        </h2>
        {preview.error ? (
          <InlineError error={preview.error} />
        ) : preview.data ? (
          <div className={t.mail}>
            <p className={t.mailSubject}>{preview.data.subject}</p>
            <div className={t.mailBody}>{preview.data.body_text}</div>
          </div>
        ) : (
          <p className={styles.hint}>填寫主旨和內文後會顯示預覽。</p>
        )}
      </section>
    </div>
  );
}
