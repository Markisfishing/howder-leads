import { useRef, useState } from "react";

import { useTemplateActions, useTemplatePreview, useTemplateVariables, useTemplateVersions, useTemplates } from "../api/hooks";
import type { EmailTemplate } from "../api/types";
import { Button } from "../components/Button";
import { Empty, ErrorState, InlineError, Loading } from "../components/StateView";
import { Tag } from "../components/Tag";
import { formatDateTime } from "../lib/labels";
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

  return (
    <>
      <header className={styles.head}>
        <h1 className={styles.title}>郵件模板</h1>
        <p className={styles.meta}>
          邀請信的固定內容。修改後會存成新版本，已經產生的草稿仍然對照舊版本。內文一定要有退訂說明。
        </p>
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
          {isLoading ? (
            <Loading />
          ) : error ? (
            <ErrorState error={error} onRetry={() => void refetch()} />
          ) : !data || data.length === 0 ? (
            <Empty title="還沒有模板">按「新增模板」建立第一份，或請管理員執行初版模板種子。</Empty>
          ) : (
            <TemplateList templates={data} onEdit={(tpl) => setEditing({ kind: "edit", template: tpl })} onNotice={setNotice} />
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
                {tpl.name} <Tag tone="info">第 {tpl.version} 版</Tag>
              </p>
              <p className={styles.hint}>主旨：{tpl.subject}</p>
              <p className={styles.hint}>更新於 {formatDateTime(tpl.created_at)}</p>
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
                          onNotice(`已停用「${tpl.name}」`);
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
              ) : (
                <Button size="sm" onClick={() => setConfirmId(tpl.template_id)}>
                  停用…
                </Button>
              )}
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
  const [name, setName] = useState(template?.name ?? "");
  const [subject, setSubject] = useState(template?.subject ?? "");
  const [body, setBody] = useState(template?.body_text ?? NEW_BODY);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const preview = useTemplatePreview(useDebounced(subject), useDebounced(body));
  const mutation = template ? update : create;

  const insert = (variable: string) => {
    const el = bodyRef.current;
    const token = `{{${variable}}}`;
    const start = el?.selectionStart ?? body.length;
    const end = el?.selectionEnd ?? body.length;
    setBody(body.slice(0, start) + token + body.slice(end));
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(start + token.length, start + token.length);
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
      <section className={styles.card} aria-labelledby="tpl-edit-title">
        <h2 id="tpl-edit-title" className={styles.cardTitle}>
          {template ? `編輯「${template.name}」（存檔會變成第 ${template.version + 1} 版）` : "新增模板"}
        </h2>
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
            rows={14}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
        </label>
        <div className={t.vars}>
          <span className={styles.label}>插入變數：</span>
          {variables?.map((v) => (
            <button key={v.name} type="button" className={t.var} onClick={() => insert(v.name)} title={v.label}>
              {v.label}
            </button>
          ))}
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
      <section className={styles.card} aria-labelledby="tpl-preview-title" aria-live="polite">
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
